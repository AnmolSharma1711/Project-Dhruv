#!/usr/bin/env python3
"""
navigate_to - type a checkpoint name, Nav2 drives the robot there.

  ros2 run nav navigate_to                 interactive prompt
  ros2 run nav navigate_to p3              one goal
  ros2 run nav navigate_to p1 p4 home      visit in order (stops at the first failure)

Ctrl-C CANCELS the Nav2 goal first, so the robot stops.

Checkpoints file, first match wins:
  --ros-args -p checkpoints_file:=/path   |   env SLAM_CHECKPOINTS   |
  ~/Desktop/SLAM/slam_node/checkpoints/checkpoints.json
It must be the SAME file the `localize` node uses.
"""
import json
import math
import os
import sys
import threading
import time

import rclpy
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.utilities import remove_ros_args

DEFAULT_FILE = '~/Desktop/SLAM/slam_node/checkpoints/checkpoints.json'
STATUS_TEXT = {GoalStatus.STATUS_SUCCEEDED: 'succeeded', GoalStatus.STATUS_CANCELED: 'canceled',
               GoalStatus.STATUS_ABORTED: 'aborted'}


def yaw_to_quaternion(yaw: float):
    return 0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0)


class CheckpointNavigator(Node):
    def __init__(self):
        super().__init__('navigate_to')
        self.declare_parameter('checkpoints_file', '')
        self.declare_parameter('goal_timeout', 120.0)
        self._client = ActionClient(self, NavigateToPose, 'navigate_to_pose')
        self._dist = None

    def checkpoints_path(self):
        p = self.get_parameter('checkpoints_file').value or os.environ.get('SLAM_CHECKPOINTS', '') \
            or DEFAULT_FILE
        return os.path.expanduser(p)

    def _feedback(self, fb):
        self._dist = fb.feedback.distance_remaining

    def _cancel(self, handle):
        try:
            fut = handle.cancel_goal_async()
            t0 = time.monotonic()
            while not fut.done() and time.monotonic() - t0 < 5.0:
                time.sleep(0.05)
            print('  goal cancelled' if fut.done() else '  ! cancel not confirmed - stop Nav2 / use the power switch')
        except Exception as exc:
            print(f'  ! cancel failed: {exc}')

    def navigate(self, name, cp) -> bool:
        if not self._client.wait_for_server(timeout_sec=10.0):
            print('  X navigate_to_pose action server not available. Is the Nav2 launch running?')
            return False
        x, y, yaw = float(cp['x']), float(cp['y']), float(cp.get('yaw', 0.0))
        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = 'map'
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x, goal.pose.pose.position.y = x, y
        (goal.pose.pose.orientation.x, goal.pose.pose.orientation.y,
         goal.pose.pose.orientation.z, goal.pose.pose.orientation.w) = yaw_to_quaternion(yaw)
        print(f'  -> {name}: x={x:.2f} y={y:.2f} yaw={math.degrees(yaw):.0f} deg   (Ctrl-C = cancel and stop)')

        self._dist = None
        send = self._client.send_goal_async(goal, feedback_callback=self._feedback)
        t0 = time.monotonic()
        while not send.done():
            if time.monotonic() - t0 > 10.0:
                print('  X goal was not accepted in time'); return False
            time.sleep(0.05)
        handle = send.result()
        if not handle.accepted:
            print('  X goal rejected by Nav2'); return False

        res = handle.get_result_async()
        timeout = float(self.get_parameter('goal_timeout').value)
        t_goal, t_print = time.monotonic(), 0.0
        try:
            while not res.done():
                now = time.monotonic()
                if now - t_goal > timeout:
                    print(f'  ! timeout after {timeout:.0f} s'); self._cancel(handle); return False
                if now - t_print > 1.0 and self._dist is not None:
                    print(f'     {self._dist:.2f} m to go'); t_print = now
                time.sleep(0.1)
        except KeyboardInterrupt:
            self._cancel(handle)
            raise
        status = res.result().status
        ok = status == GoalStatus.STATUS_SUCCEEDED
        print(f'  OK reached {name}' if ok else
              f'  X {name}: {STATUS_TEXT.get(status, f"status {status}")}')
        return ok


def show(cps):
    print(f'\n  {"NAME":<10}{"X":>8}{"Y":>8}{"YAW":>8}')
    for n, c in cps.items():
        print(f'  {n:<10}{c["x"]:>8.2f}{c["y"]:>8.2f}{math.degrees(c.get("yaw", 0.0)):>7.0f}d')
    print()


def main(args=None):
    # Keep Python's own Ctrl-C (KeyboardInterrupt) so we can cancel the goal before exiting.
    try:
        from rclpy.signals import SignalHandlerOptions
        rclpy.init(args=args, signal_handler_options=SignalHandlerOptions.NO)
    except ImportError:
        rclpy.init(args=args)
    node = CheckpointNavigator()
    threading.Thread(target=rclpy.spin, args=(node,), daemon=True).start()
    code = 0
    try:
        path = node.checkpoints_path()
        try:
            with open(path) as f:
                cps = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            print(f'ERROR reading checkpoints file {path}: {exc}', file=sys.stderr)
            sys.exit(1)
        print(f'Checkpoints file: {path}')
        names = remove_ros_args(args)[1:] if args is not None else remove_ros_args()[1:]
        if names:
            for n in names:
                if n not in cps:
                    print(f'ERROR: unknown checkpoint "{n}". Known: {", ".join(cps)}', file=sys.stderr)
                    code = 1; break
                if not node.navigate(n, cps[n]):
                    code = 1; break
        else:
            show(cps)
            print('Type a checkpoint name.  l = list, q = quit.')
            while True:
                try:
                    s = input('navigate> ').strip()
                except EOFError:
                    break
                if s in ('q', 'quit', 'exit'):
                    break
                if s in ('l', 'list'):
                    show(cps)
                elif s in cps:
                    node.navigate(s, cps[s])
                elif s:
                    print(f'  unknown checkpoint "{s}"')
    except KeyboardInterrupt:
        print('\nstopped')
        code = 130
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
    sys.exit(code)


if __name__ == '__main__':
    main()
