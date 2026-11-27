#!/usr/bin/env python3
"""
nav2_bringup.launch.py - Nav2 navigation + the /cmd_vel_smoothed -> Arduino bridge.

NOT started here (run separately, as before): IMU, rf2o+LiDAR, EKF and `localize`
(map server + AMCL). 

IMPORTANT: this launch starts its OWN serial bridge (cmd_vel_bridge). Do NOT run
slam_node's drive.launch.py at the same time - both would fight over the serial port.

Arguments:
  odom_topic     odometry topic used by bt_navigator, controller and smoother
  robot_radius   metres from robot centre to its outer edge (TODO: verify by measuring)
  serial_port    Arduino device
  dry_run        true = bridge only logs commands (no serial port)
  params_file    Nav2 params (default: config/nav2_params.yaml)
"""
import os
import tempfile

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue

from nav.params_util import rewrite_params


def _nodes(context, *args, **kwargs):
    pkg = get_package_share_directory('nav')
    odom = LaunchConfiguration('odom_topic').perform(context)
    radius = float(LaunchConfiguration('robot_radius').perform(context))
    with open(LaunchConfiguration('params_file').perform(context)) as f:
        params = rewrite_params(yaml.safe_load(f), odom, radius)
    tmp = tempfile.NamedTemporaryFile('w', suffix='.yaml', prefix='anmol_nav2_', delete=False)
    yaml.safe_dump(params, tmp)
    tmp.close()

    def nav2(package, executable, name):
        return Node(package=package, executable=executable, name=name, output='screen',
                    respawn=True, respawn_delay=2.0, parameters=[tmp.name])

    bridge = Node(
        package='nav', executable='cmd_vel_bridge', name='cmd_vel_bridge', output='screen',
        respawn=True, respawn_delay=3.0,
        parameters=[os.path.join(pkg, 'config', 'bridge.yaml'),
                    {'port': ParameterValue(LaunchConfiguration('serial_port'), value_type=str),
                     'dry_run': ParameterValue(LaunchConfiguration('dry_run'), value_type=bool)}])

    lifecycle = Node(
        package='nav2_lifecycle_manager', executable='lifecycle_manager',
        name='lifecycle_manager_navigation', output='screen',
        parameters=[{'autostart': True, 'bond_timeout': 10.0,
                     'attempt_respawn_reconnection': True,
                     'node_names': ['planner_server', 'controller_server',
                                    'behavior_server', 'bt_navigator', 'velocity_smoother']}])

    return [
        LogInfo(msg=f'[nav] odom_topic={odom}  robot_radius={radius} m  params={tmp.name}'),
        LogInfo(msg='[nav] This launch starts its OWN serial bridge. '
                    'Do NOT run slam_node drive.launch.py at the same time.'),
        nav2('nav2_planner', 'planner_server', 'planner_server'),
        nav2('nav2_controller', 'controller_server', 'controller_server'),
        nav2('nav2_behaviors', 'behavior_server', 'behavior_server'),
        nav2('nav2_bt_navigator', 'bt_navigator', 'bt_navigator'),
        nav2('nav2_velocity_smoother', 'velocity_smoother', 'velocity_smoother'),
        lifecycle,
        bridge,
    ]


def generate_launch_description():
    pkg = get_package_share_directory('nav')
    return LaunchDescription([
        DeclareLaunchArgument('odom_topic', default_value='/odometry/filtered'),
        DeclareLaunchArgument('robot_radius', default_value='0.13',
                              description='TODO: verify - centre to outer edge, metres'),
        DeclareLaunchArgument('serial_port', default_value='/dev/ttyACM0'),
        DeclareLaunchArgument('dry_run', default_value='false'),
        DeclareLaunchArgument('params_file',
                              default_value=os.path.join(pkg, 'config', 'nav2_params.yaml')),
        OpaqueFunction(function=_nodes),
    ])
