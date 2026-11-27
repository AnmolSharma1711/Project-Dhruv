#!/usr/bin/env python3
"""
nav2_bringup.launch.py
======================
Starts the full Nav2 stack + cmd_vel_bridge for the mecanum robot.

IMPORTANT — What this launch file does NOT start:
  • map_server      — map is served by localization_node (Terminal 4)
  • amcl            — handled by localization_node (Terminal 4)
  • static_transform_publisher for base_link→laser — started by kushal_odom (T2)
  • ekf_node        — started separately (Terminal 3)

This launch file only owns Nav2 navigation nodes + the serial bridge.

Usage:
  ros2 launch anmol nav2_bringup.launch.py
  ros2 launch anmol nav2_bringup.launch.py dry_run:=true  # no serial port
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, EmitEvent, LogInfo
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    # ------------------------------------------------------------------ #
    # Paths
    # ------------------------------------------------------------------ #
    pkg_dir = get_package_share_directory('anmol')
    nav2_params_file = os.path.join(pkg_dir, 'config', 'nav2_params.yaml')

    # ------------------------------------------------------------------ #
    # Launch arguments
    # ------------------------------------------------------------------ #
    declare_dry_run = DeclareLaunchArgument(
        'dry_run',
        default_value='false',
        description='If true, cmd_vel_bridge logs commands but does not open serial port')

    declare_serial_port = DeclareLaunchArgument(
        'serial_port',
        default_value='/dev/ttyACM0',
        description='Arduino serial device path')

    declare_use_sim_time = DeclareLaunchArgument(
        'use_sim_time',
        default_value='false',
        description='Use simulation clock')

    dry_run      = LaunchConfiguration('dry_run')
    serial_port  = LaunchConfiguration('serial_port')
    use_sim_time = LaunchConfiguration('use_sim_time')

    # ------------------------------------------------------------------ #
    # Nav2 nodes
    # ------------------------------------------------------------------ #
    planner_server = Node(
        package='nav2_planner',
        executable='planner_server',
        name='planner_server',
        output='screen',
        respawn=True,
        respawn_delay=2.0,
        parameters=[nav2_params_file, {'use_sim_time': use_sim_time}])

    controller_server = Node(
        package='nav2_controller',
        executable='controller_server',
        name='controller_server',
        output='screen',
        respawn=True,
        respawn_delay=2.0,
        parameters=[nav2_params_file, {'use_sim_time': use_sim_time}])

    smoother_server = Node(
        package='nav2_smoother',
        executable='smoother_server',
        name='smoother_server',
        output='screen',
        respawn=True,
        respawn_delay=2.0,
        parameters=[nav2_params_file, {'use_sim_time': use_sim_time}])

    behavior_server = Node(
        package='nav2_behaviors',
        executable='behavior_server',
        name='behavior_server',
        output='screen',
        respawn=True,
        respawn_delay=2.0,
        parameters=[nav2_params_file, {'use_sim_time': use_sim_time}])

    bt_navigator = Node(
        package='nav2_bt_navigator',
        executable='bt_navigator',
        name='bt_navigator',
        output='screen',
        respawn=True,
        respawn_delay=2.0,
        parameters=[nav2_params_file, {'use_sim_time': use_sim_time}])

    velocity_smoother = Node(
        package='nav2_velocity_smoother',
        executable='velocity_smoother',
        name='velocity_smoother',
        output='screen',
        respawn=True,
        respawn_delay=2.0,
        parameters=[nav2_params_file, {'use_sim_time': use_sim_time}])

    lifecycle_manager = Node(
        package='nav2_lifecycle_manager',
        executable='lifecycle_manager',
        name='lifecycle_manager_navigation',
        output='screen',
        parameters=[{
            'use_sim_time': use_sim_time,
            'autostart': True,
            'bond_timeout': 4.0,
            'node_names': [
                'planner_server',
                'controller_server',
                'smoother_server',
                'behavior_server',
                'bt_navigator',
                'velocity_smoother',
            ],
        }])

    # ------------------------------------------------------------------ #
    # cmd_vel bridge  (Nav2 /cmd_vel → Arduino serial)
    # ------------------------------------------------------------------ #
    cmd_vel_bridge = Node(
        package='anmol',
        executable='cmd_vel_bridge',
        name='cmd_vel_bridge',
        output='screen',
        respawn=True,
        respawn_delay=3.0,
        parameters=[{
            'serial_port':   serial_port,
            'baud_rate':     115200,
            'linear_scale':  514.0,
            'angular_scale': 225.0,
            'pwm_max':       180,
            'watchdog_timeout': 1.5,
            'dry_run':       dry_run,
        }])

    return LaunchDescription([
        declare_dry_run,
        declare_serial_port,
        declare_use_sim_time,
        LogInfo(msg='[anmol] Starting Nav2 navigation stack...'),
        LogInfo(msg='[anmol] Assumes localization_node (AMCL) already running in Terminal 4'),
        planner_server,
        controller_server,
        smoother_server,
        behavior_server,
        bt_navigator,
        velocity_smoother,
        lifecycle_manager,
        cmd_vel_bridge,
    ])
