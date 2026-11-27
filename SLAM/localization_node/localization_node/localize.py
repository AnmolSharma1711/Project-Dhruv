#!/usr/bin/env python3
"""
localize — one command: starts map server + AMCL, asks where the robot roughly is
(a checkpoint name), sets that as the start pose, and waits until AMCL is sure.

    ros2 run localization_node localize
    ros2 run localization_node localize --ros-args -p map:=/home/you/SLAM/maps/my_map.yaml

Keep this terminal open while the robot is driving: it runs the map server + AMCL.
"""
import json
import math
import os
import signal
import subprocess
import sys
import threading
import time

import rclpy
import tf2_ros
from geometry_msgs.msg import PoseWithCovarianceStamped
from lifecycle_msgs.srv import GetState
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.time import Time
from std_srvs.srv import Empty

LOG = '/tmp/localization_server.log'


class Localize(Node):
    def __init__(self):
        super().__init__('localize_helper')
        self.declare_parameter('map', os.path.expanduser('~/SLAM/maps/my_map.yaml'))
        self.declare_parameter('checkpoints_file', '')
        self.declare_parameter('xy_std_max', 0.15)     # m   "sure enough" limits
        self.declare_parameter('yaw_std_max', 0.15)    # rad
        self.declare_parameter('timeout', 60.0)        # s
        self.g = lambda k: self.get_parameter(k).value

        self.pose_pub = self.create_publisher(PoseWithCovarianceStamped, '/initialpose', 10)
        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                         durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.last_amcl = None
        self.create_subscription(PoseWithCovarianceStamped, '/amcl_pose', self._on_amcl, qos)
        self.state_cli = self.create_client(GetState, '/amcl/get_state')
        self.nomotion_cli = self.create_client(Empty, '/request_nomotion_update')
        self.tf_buf = tf2_ros.Buffer()
        self.tf_lis = tf2_ros.TransformListener(self.tf_buf, self)

    def _on_amcl(self, m):
        self.last_amcl = (time.monotonic(), m)

    # ── helpers ─────────────────────────────────────────────────────────────
    def load_checkpoints(self):
        path = self.g('checkpoints_file')
        if not path:
            try:
                from ament_index_python.packages import get_package_share_directory
                path = os.path.join(get_package_share_directory('slam_node'),
                                    'checkpoints', 'checkpoints.json')
            except Exception:
                path = os.path.expanduser('~/SLAM/slam_node/checkpoints/checkpoints.json')
        with open(path) as f:
            return json.load(f), path

    def amcl_active(self):
        if not self.state_cli.wait_for_service(timeout_sec=0.2):
            return False
        fut = self.state_cli.call_async(GetState.Request())
        t0 = time.monotonic()
        while not fut.done() and time.monotonic() - t0 < 1.0:
            time.sleep(0.05)
        return fut.done() and fut.result().current_state.id == 3     # 3 = ACTIVE

    def publish_start_pose(self, p):
        m = PoseWithCovarianceStamped()
        m.header.frame_id = 'map'
        m.header.stamp = self.get_clock().now().to_msg()
        m.pose.pose.position.x, m.pose.pose.position.y = p['x'], p['y']
        m.pose.pose.orientation.z = math.sin(p['yaw'] / 2)
        m.pose.pose.orientation.w = math.cos(p['yaw'] / 2)
        cov = [0.0] * 36
        cov[0] = cov[7] = 0.09          # "I am within about 30 cm"
        cov[35] = 0.09                  # "... and about 17 degrees"
        m.pose.covariance = cov
        for _ in range(3):
            self.pose_pub.publish(m)
            time.sleep(0.5)

    def wait_until_sure(self):
        t_start = time.monotonic()
        self.last_amcl = None
        good = 0
        while time.monotonic() - t_start < self.g('timeout'):
            if self.nomotion_cli.service_is_ready():
                self.nomotion_cli.call_async(Empty.Request())     # refine without moving
            time.sleep(1.0)
            if self.last_amcl is None:
                print('  … waiting for first AMCL estimate')
                continue
            c = self.last_amcl[1].pose.covariance
            xy = math.sqrt(max(c[0], c[7]))
            yaw = math.sqrt(max(c[35], 0.0))
            tf_ok = self.tf_buf.can_transform('map', 'base_link', Time())
            print(f'  … uncertainty: {xy:.2f} m, {math.degrees(yaw):.0f}°')
            if xy < self.g('xy_std_max') and yaw < self.g('yaw_std_max') and tf_ok:
                good += 1
                if good >= 3:                 # stable for 3 checks in a row
                    return True
            else:
                good = 0
        return False


def main(args=None):
    rclpy.init(args=args)
    node = Localize()

    server = subprocess.Popen(
        ['ros2', 'launch', 'localization_node', 'localization.launch.py',
         f'map:={node.g("map")}'],
        stdout=open(LOG, 'w'), stderr=subprocess.STDOUT, preexec_fn=os.setsid)

    def shutdown(*_):
        try:
            os.killpg(os.getpgid(server.pid), signal.SIGINT)
            server.wait(timeout=5)
        except Exception:
            pass
        node.destroy_node()
        rclpy.try_shutdown()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    threading.Thread(target=rclpy.spin, args=(node,), daemon=True).start()

    try:
        cps, path = node.load_checkpoints()
        print(f'\nMap: {node.g("map")}\nCheckpoints: {path}\nServer log: {LOG}\n')
        print('Starting map server + AMCL ...')
        t0 = time.monotonic()
        while not node.amcl_active():
            if server.poll() is not None or time.monotonic() - t0 > 40:
                print(f'✗ AMCL did not start. See {LOG}')
                return shutdown()
            time.sleep(0.5)
        print('✓ Map server + AMCL running.\n')

        while True:
            print('Checkpoints:', ', '.join(cps))
            name = input('Where is the robot roughly? (checkpoint name, q = quit): ').strip()
            if name in ('q', 'quit'):
                break
            if name not in cps:
                print(f'  ✗ "{name}" is not in the checkpoints file.\n')
                continue
            node.publish_start_pose(cps[name])
            print('  Start pose sent. If it stays unsure, drive the robot a little by hand.')
            if node.wait_until_sure():
                print('\n✓ Localized — ready to control\n')
                print('Keep this terminal open. Type another name to re-set the position, or q to quit.\n')
            else:
                print(f'\n✗ Not sure yet. Check the robot is near "{name}" and facing the right way,')
                print('  move it a little, then type the name again.\n')
    except (KeyboardInterrupt, EOFError):
        pass
    shutdown()


if __name__ == '__main__':
    main()
