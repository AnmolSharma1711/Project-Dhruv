#!/usr/bin/env python3
"""
navigate_to.py  —  Checkpoint navigation CLI for the SLAM robot.

Usage:
  ros2 run anmol navigate_to <checkpoint_name>
  ros2 run anmol navigate_to p1
  ros2 run anmol navigate_to home
  ros2 run anmol navigate_to          # interactive — lists all checkpoints

The checkpoint yaw is taken directly from checkpoints.json and converted to
a quaternion.  This avoids the logical error of always sending {w: 1.0}
(= yaw 0° = facing east), which forces the robot to spin to the wrong
heading at every destination.
"""

import sys
import json
import math

import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from rclpy.duration import Duration
from nav2_msgs.action import NavigateToPose
from geometry_msgs.msg import PoseStamped

# ---------------------------------------------------------------------------
# Path to checkpoints file — adjust if map is moved
# ---------------------------------------------------------------------------
CHECKPOINTS_FILE = '/home/dhruv/Desktop/SLAM/saved_map/checkpoints.json'


def yaw_to_quaternion(yaw: float):
    """Convert a yaw angle (radians) to a geometry_msgs quaternion tuple (x,y,z,w)."""
    half = yaw / 2.0
    return (0.0, 0.0, math.sin(half), math.cos(half))


class CheckpointNavigator(Node):
    """ROS 2 action client that sends a NavigateToPose goal and waits for the result."""

    def __init__(self):
        super().__init__('navigate_to')
        self._client = ActionClient(self, NavigateToPose, '/navigate_to_pose')

    def navigate(self, checkpoint: dict, name: str) -> bool:
        """
        Send a goal to Nav2 and block until it completes.
        Returns True on success, False on failure/cancel.
        """
        self.get_logger().info(
            f"⏳  Waiting for /navigate_to_pose action server …"
        )
        if not self._client.wait_for_server(timeout_sec=10.0):
            self.get_logger().error(
                "✗  /navigate_to_pose action server not available after 10 s. "
                "Is Nav2 running? (ros2 launch anmol nav2_bringup.launch.py)"
            )
            return False

        # Build the goal message
        goal_msg = NavigateToPose.Goal()
        goal_msg.pose = PoseStamped()
        goal_msg.pose.header.frame_id = 'map'
        goal_msg.pose.header.stamp = self.get_clock().now().to_msg()

        x = float(checkpoint['x'])
        y = float(checkpoint['y'])
        yaw = float(checkpoint.get('yaw', 0.0))

        goal_msg.pose.pose.position.x = x
        goal_msg.pose.pose.position.y = y
        goal_msg.pose.pose.position.z = 0.0

        qx, qy, qz, qw = yaw_to_quaternion(yaw)
        goal_msg.pose.pose.orientation.x = qx
        goal_msg.pose.pose.orientation.y = qy
        goal_msg.pose.pose.orientation.z = qz
        goal_msg.pose.pose.orientation.w = qw

        self.get_logger().info(
            f"🚀  Navigating to '{name}':  "
            f"x={x:.3f} m  y={y:.3f} m  yaw={math.degrees(yaw):.1f}°"
        )

        # Send goal asynchronously, then spin until done
        send_future = self._client.send_goal_async(goal_msg)
        rclpy.spin_until_future_complete(self, send_future)

        goal_handle = send_future.result()
        if not goal_handle.accepted:
            self.get_logger().error('✗  Goal rejected by Nav2.')
            return False

        self.get_logger().info('  Goal accepted — robot is moving …')

        result_future = goal_handle.get_result_async()
        rclpy.spin_until_future_complete(self, result_future)

        # action_msgs/GoalStatus: SUCCEEDED = 4
        status = result_future.result().status
        if status == 4:
            self.get_logger().info(f"✅  Reached '{name}'!")
            return True
        else:
            self.get_logger().error(
                f"✗  Navigation to '{name}' failed — status code {status}. "
                f"(3=Cancelled, 5=Aborted, 6=Unknown)"
            )
            return False


def load_checkpoints(path: str) -> dict:
    """Load checkpoints.json and return the dict."""
    try:
        with open(path, 'r') as fh:
            data = json.load(fh)
        return data
    except FileNotFoundError:
        print(f"ERROR: Checkpoints file not found: {path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"ERROR: Invalid JSON in checkpoints file: {exc}", file=sys.stderr)
        sys.exit(1)


def print_checkpoints(checkpoints: dict):
    """Pretty-print all available checkpoints."""
    print("\nAvailable checkpoints:")
    print(f"  {'Name':<10}  {'X (m)':>8}  {'Y (m)':>8}  {'Yaw (°)':>9}")
    print(f"  {'-'*10}  {'-'*8}  {'-'*8}  {'-'*9}")
    for name, cp in checkpoints.items():
        yaw_deg = math.degrees(float(cp.get('yaw', 0.0)))
        print(f"  {name:<10}  {cp['x']:>8.3f}  {cp['y']:>8.3f}  {yaw_deg:>8.1f}°")
    print()


def main(args=None):
    rclpy.init(args=args)

    checkpoints = load_checkpoints(CHECKPOINTS_FILE)

    # Determine target checkpoint name
    argv = [a for a in sys.argv[1:] if not a.startswith('--ros-args')]
    if argv:
        name = argv[0].strip()
    else:
        # Interactive mode
        print_checkpoints(checkpoints)
        try:
            name = input('Navigate to (checkpoint name): ').strip()
        except (EOFError, KeyboardInterrupt):
            print('\nAborted.')
            rclpy.shutdown()
            return

    if name not in checkpoints:
        print(
            f"\nERROR: Checkpoint '{name}' not found.\n"
            f"Available: {', '.join(checkpoints.keys())}\n",
            file=sys.stderr
        )
        rclpy.shutdown()
        sys.exit(1)

    node = CheckpointNavigator()
    success = node.navigate(checkpoints[name], name)
    node.destroy_node()
    rclpy.shutdown()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
