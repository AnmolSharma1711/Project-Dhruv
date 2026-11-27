#!/usr/bin/env python3
"""
cmd_vel_bridge - /cmd_vel_smoothed (Twist from Nav2) -> Arduino over USB serial.

Protocol (akshat/motor_control/arduino.ino), newline terminated, 115200 baud:
  MODE:AUTO          give the Jetson control (sent once at start)
  <MIX,Vx,Vy,W>      Vx forward(+), Vy sideways (ALWAYS 0 here), W turn left/CCW(+)
  STOP               stop now
  MODE:MANUAL        hand control back (sent on shutdown)
Values are raw motor power (firmware cap 180). The firmware stops by itself after 1.5 s of
silence, so this node resends the latest command at `rate_hz`.

Settings live in config/bridge.yaml (measured: 0.148 m/s and 2.285 rad/s at power 180).
"""
import sys
import threading
import time

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy

from nav.drive_math import format_mix, sanitize, twist_to_mix

try:
    import serial
except ImportError:                       # pragma: no cover
    serial = None


class CmdVelBridge(Node):
    def __init__(self):
        super().__init__('cmd_vel_bridge')
        d = self.declare_parameter
        d('port', '/dev/ttyACM0')
        d('baud', 115200)
        d('cmd_topic', '/cmd_vel_smoothed')
        d('pwm_per_mps', 1216.0)
        d('pwm_per_radps', 78.8)
        d('min_pwm', 25)
        d('max_pwm', 180)
        d('drive_sign', 1)
        d('turn_sign', 1)
        d('cmd_timeout', 0.5)
        d('rate_hz', 20.0)
        d('dry_run', False)
        g = lambda k: self.get_parameter(k).value
        self.g = g

        self._lock = threading.Lock()           # one writer at a time
        self._stop_evt = threading.Event()
        self._ser = None
        self._cmd = (0.0, 0.0)                  # (vx, wz)
        self._cmd_t = None
        self._fail = 0
        self._last_logged = None

        if g('dry_run'):
            self.get_logger().warn('DRY-RUN: no serial port opened, commands are only logged')
        else:
            self._open_serial()

        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT,
                         durability=DurabilityPolicy.VOLATILE)
        self.create_subscription(Twist, g('cmd_topic'), self._on_cmd, qos)
        self.create_timer(1.0 / g('rate_hz'), self._tick)
        self.get_logger().info(
            f'bridge ready: {g("cmd_topic")} -> {g("port")}  '
            f'{g("pwm_per_mps")} pwr/(m/s), {g("pwm_per_radps")} pwr/(rad/s), '
            f'power {g("min_pwm")}..{g("max_pwm")}  (sideways always 0)')

    # ── serial ──────────────────────────────────────────────────────────────
    def _open_serial(self):
        if serial is None:
            raise RuntimeError('pyserial missing: sudo apt install python3-serial')
        port, baud = self.g('port'), self.g('baud')
        try:
            self._ser = serial.Serial(port, baud, timeout=0.1)
        except Exception as exc:                # fail loudly; launch respawn will retry
            raise RuntimeError(f'cannot open serial {port}: {exc}')
        time.sleep(2.0)                         # UNO R4 resets when the port opens
        self._ser.reset_input_buffer()
        self._write('MODE:AUTO')
        threading.Thread(target=self._reader, daemon=True).start()
        self.get_logger().info(f'serial open {port} @ {baud}, MODE:AUTO sent')

    def _reader(self):
        """Read and discard the Arduino's replies so its output buffer never fills."""
        while not self._stop_evt.is_set():
            try:
                self._ser.readline()
            except Exception:
                time.sleep(0.1)

    def _write(self, text: str):
        if self.g('dry_run'):
            if text != self._last_logged:
                self.get_logger().info(f'[DRY-RUN] -> {text}')
                self._last_logged = text
            return
        with self._lock:
            try:
                self._ser.write((text + '\n').encode('ascii'))
                self._ser.flush()
                self._fail = 0
            except Exception as exc:
                self._fail += 1
                if self._fail == 1:
                    self.get_logger().error(f'serial write failed: {exc}')

    # ── ROS ─────────────────────────────────────────────────────────────────
    def _on_cmd(self, m: Twist):
        # linear.y is deliberately ignored: no sideways motion
        self._cmd = (sanitize(m.linear.x), sanitize(m.angular.z))
        self._cmd_t = time.monotonic()

    def _tick(self):
        if self._fail >= 20:                    # unplugged / reset: exit, launch respawns us
            raise RuntimeError('serial connection lost')
        g = self.g
        fresh = self._cmd_t is not None and time.monotonic() - self._cmd_t < g('cmd_timeout')
        vx, wz = self._cmd if fresh else (0.0, 0.0)
        a, b, c = twist_to_mix(vx, wz, g('pwm_per_mps'), g('pwm_per_radps'),
                               g('min_pwm'), g('max_pwm'), g('drive_sign'), g('turn_sign'))
        self._write(format_mix(a, b, c))

    def shutdown_robot(self):
        """Always leave the robot stopped and hand control back."""
        self._stop_evt.set()
        for text in ('STOP', 'STOP', 'MODE:MANUAL'):
            self._write(text)
            time.sleep(0.05)
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass


def main(args=None):
    rclpy.init(args=args)
    node = None
    code = 0
    try:
        node = CmdVelBridge()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f'[cmd_vel_bridge] fatal: {exc}', file=sys.stderr)
        code = 1
    finally:
        if node is not None:
            node.shutdown_robot()
            node.destroy_node()
        rclpy.try_shutdown()
    sys.exit(code)


if __name__ == '__main__':
    main()
