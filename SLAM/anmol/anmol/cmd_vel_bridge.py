#!/usr/bin/env python3
"""
cmd_vel_bridge.py
=================
Subscribes to /cmd_vel (geometry_msgs/Twist) published by Nav2 and
translates it to the Arduino serial protocol used by Akshat's firmware.

Arduino protocol  (akshat/motor_control/arduino.ino):
  MODE:AUTO          — switch firmware to autonomous mode (sent once on start)
  <MIX,Vx,Vy,W>     — mecanum drive command  (integers -180 … +180)
  STOP               — emergency stop

Wheel orientation — DIAMOND (X-shape, 45° rotated from standard cross):
  Forward/backward mapping is identical to cross orientation.
  Strafe (Vy) sign is NEGATED vs standard cross to compensate for the
  physical swap of strafe and diagonal axes in the diamond layout.

Scaling (derived from robot specs):
  Max linear  = 0.35 m/s  →  PWM 180   ⟹  LINEAR_SCALE  ≈ 514
  Max angular = 0.80 rad/s →  PWM 180   ⟹  ANGULAR_SCALE ≈ 225

Serial device: /dev/ttyACM0  (Arduino UNO R4 on Jetson Orin Nano)
Baud rate    : 115200
"""

import math
import threading
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy

from geometry_msgs.msg import Twist

try:
    import serial
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False


# ---------------------------------------------------------------------------
# Tunable constants
# ---------------------------------------------------------------------------
SERIAL_PORT      = '/dev/ttyACM0'
BAUD_RATE        = 115200
LINEAR_SCALE     = 514      # PWM units per m/s
ANGULAR_SCALE    = 225      # PWM units per rad/s
PWM_MAX          = 180      # Firmware clamps to ±180 internally, but we cap here too
WATCHDOG_TIMEOUT = 1.5      # seconds — stop robot if no cmd_vel received


class CmdVelBridge(Node):
    def __init__(self):
        super().__init__('cmd_vel_bridge')

        # ------------------------------------------------------------------ #
        # Parameters (overridable at launch time)
        # ------------------------------------------------------------------ #
        self.declare_parameter('serial_port',   SERIAL_PORT)
        self.declare_parameter('baud_rate',     BAUD_RATE)
        self.declare_parameter('linear_scale',  float(LINEAR_SCALE))
        self.declare_parameter('angular_scale', float(ANGULAR_SCALE))
        self.declare_parameter('pwm_max',       PWM_MAX)
        self.declare_parameter('watchdog_timeout', WATCHDOG_TIMEOUT)
        self.declare_parameter('dry_run', False)   # True = log only, no serial

        port    = self.get_parameter('serial_port').value
        baud    = self.get_parameter('baud_rate').value
        self.lin_scale  = self.get_parameter('linear_scale').value
        self.ang_scale  = self.get_parameter('angular_scale').value
        self.pwm_max    = self.get_parameter('pwm_max').value
        self.wd_timeout = self.get_parameter('watchdog_timeout').value
        self.dry_run    = self.get_parameter('dry_run').value

        # ------------------------------------------------------------------ #
        # Serial connection
        # ------------------------------------------------------------------ #
        self._ser = None
        if not self.dry_run:
            if not SERIAL_AVAILABLE:
                self.get_logger().error('pyserial not installed — run: pip3 install pyserial')
                raise RuntimeError('pyserial missing')
            self._open_serial(port, baud)
        else:
            self.get_logger().warn('DRY-RUN mode: no serial port opened')

        # ------------------------------------------------------------------ #
        # QoS — match Nav2 controller output (Best Effort, volatile)
        # ------------------------------------------------------------------ #
        qos = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
        )

        self._sub = self.create_subscription(
            Twist, '/cmd_vel_smoothed', self._cmd_vel_cb, qos)

        # ------------------------------------------------------------------ #
        # Watchdog timer — stops robot if Nav2 goes silent
        # ------------------------------------------------------------------ #
        self._last_cmd_time = time.time()
        self._watchdog_active = True
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop, daemon=True)
        self._watchdog_thread.start()

        self.get_logger().info(
            f'cmd_vel_bridge ready  port={port}  baud={baud}  '
            f'lin_scale={self.lin_scale}  ang_scale={self.ang_scale}  '
            f'dry_run={self.dry_run}')

    # ---------------------------------------------------------------------- #
    # Serial helpers
    # ---------------------------------------------------------------------- #
    def _open_serial(self, port: str, baud: int):
        """Open serial port and switch Arduino to AUTO mode."""
        try:
            self._ser = serial.Serial(port, baud, timeout=1.0)
            time.sleep(2.0)          # wait for Arduino bootloader to settle
            self._ser.reset_input_buffer()
            self._send_raw('MODE:AUTO')
            self.get_logger().info(f'Serial opened: {port}  →  MODE:AUTO sent')
        except serial.SerialException as exc:
            self.get_logger().error(f'Cannot open serial {port}: {exc}')
            self._ser = None

    def _send_raw(self, msg: str):
        """Write a newline-terminated string to the serial port."""
        if self._ser and self._ser.is_open:
            try:
                self._ser.write((msg + '\n').encode('ascii'))
                self._ser.flush()
            except serial.SerialException as exc:
                self.get_logger().error(f'Serial write error: {exc}')
        elif self.dry_run:
            self.get_logger().info(f'[DRY-RUN] Serial → {msg}')

    # ---------------------------------------------------------------------- #
    # Twist → PWM conversion  (diamond orientation)
    # ---------------------------------------------------------------------- #
    def _twist_to_pwm(self, msg: Twist):
        """
        Convert a Twist message to (vx_pwm, vy_pwm, w_pwm).

        Diamond (X) orientation correction:
          Nav2 sends linear.y = strafe intent.
          In a diamond layout the physical strafe and diagonal axes are swapped
          relative to the firmware's expectation (which assumes cross layout).
          Fix: negate vy before sending to Arduino.
          (Forward/backward = linear.x, angular = angular.z — both unchanged.)
        """
        vx =  msg.linear.x          # forward (+) / backward (-)
        vy = -msg.linear.y          # NEGATED for diamond orientation
        wz =  msg.angular.z         # CCW positive (+W = CCW in Arduino firmware)

        vx_pwm = self._clamp(int(vx * self.lin_scale))
        vy_pwm = self._clamp(int(vy * self.lin_scale))
        w_pwm  = self._clamp(int(wz * self.ang_scale))
        return vx_pwm, vy_pwm, w_pwm

    def _clamp(self, val: int) -> int:
        return max(-self.pwm_max, min(self.pwm_max, val))

    # ---------------------------------------------------------------------- #
    # Subscriber callback
    # ---------------------------------------------------------------------- #
    def _cmd_vel_cb(self, msg: Twist):
        self._last_cmd_time = time.time()
        vx_pwm, vy_pwm, w_pwm = self._twist_to_pwm(msg)

        cmd = f'<MIX,{vx_pwm},{vy_pwm},{w_pwm}>'
        self._send_raw(cmd)

        self.get_logger().debug(
            f'/cmd_vel  vx={msg.linear.x:.3f}  vy={msg.linear.y:.3f}  '
            f'wz={msg.angular.z:.3f}  →  {cmd}')

    # ---------------------------------------------------------------------- #
    # Watchdog
    # ---------------------------------------------------------------------- #
    def _watchdog_loop(self):
        """Background thread: send STOP if no cmd_vel for wd_timeout seconds."""
        while self._watchdog_active:
            time.sleep(0.1)
            if time.time() - self._last_cmd_time > self.wd_timeout:
                self._send_raw('STOP')
                # Reset so we don't spam STOP every 0.1 s
                self._last_cmd_time = time.time()

    # ---------------------------------------------------------------------- #
    # Cleanup
    # ---------------------------------------------------------------------- #
    def destroy_node(self):
        self._watchdog_active = False
        self._send_raw('STOP')
        time.sleep(0.1)
        if not self.dry_run:
            self._send_raw('MODE:MANUAL')
            time.sleep(0.1)
        if self._ser and self._ser.is_open:
            self._ser.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = CmdVelBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
