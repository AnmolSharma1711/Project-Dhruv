#!/usr/bin/env python3
"""
full_nav.launch.py
==================
Convenience wrapper that launches the complete navigation stack.
Equivalent to:  ros2 launch anmol nav2_bringup.launch.py

Split into a separate file so future integrators can include just
nav2_bringup.launch.py without the bridge, or the bridge standalone.

Usage:
  ros2 launch anmol full_nav.launch.py
  ros2 launch anmol full_nav.launch.py dry_run:=true
  ros2 launch anmol full_nav.launch.py serial_port:=/dev/ttyUSB0
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    pkg_dir = get_package_share_directory('anmol')

    declare_dry_run = DeclareLaunchArgument(
        'dry_run', default_value='false',
        description='Skip serial port — log commands only')

    declare_serial_port = DeclareLaunchArgument(
        'serial_port', default_value='/dev/ttyACM0',
        description='Arduino serial device')

    declare_use_sim_time = DeclareLaunchArgument(
        'use_sim_time', default_value='false',
        description='Use simulation clock')

    nav2_bringup = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_dir, 'launch', 'nav2_bringup.launch.py')),
        launch_arguments={
            'dry_run':      LaunchConfiguration('dry_run'),
            'serial_port':  LaunchConfiguration('serial_port'),
            'use_sim_time': LaunchConfiguration('use_sim_time'),
        }.items())

    return LaunchDescription([
        declare_dry_run,
        declare_serial_port,
        declare_use_sim_time,
        nav2_bringup,
    ])
