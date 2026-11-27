#!/usr/bin/env python3
"""full_nav.launch.py - convenience wrapper, same arguments as nav2_bringup.launch.py."""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration

ARGS = {'odom_topic': '/odometry/filtered', 'robot_radius': '0.13',
        'serial_port': '/dev/ttyACM0', 'dry_run': 'false'}


def generate_launch_description():
    pkg = get_package_share_directory('nav')
    return LaunchDescription(
        [DeclareLaunchArgument(k, default_value=v) for k, v in ARGS.items()] + [
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(os.path.join(pkg, 'launch', 'nav2_bringup.launch.py')),
                launch_arguments={k: LaunchConfiguration(k) for k in ARGS}.items())])
