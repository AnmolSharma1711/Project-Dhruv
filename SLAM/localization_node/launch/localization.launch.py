"""Map server + AMCL + lifecycle manager (replaces slam_toolbox mapping)."""
import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    share = get_package_share_directory('localization_node')
    default_map = os.path.expanduser('~/SLAM/maps/my_map.yaml')

    return LaunchDescription([
        DeclareLaunchArgument('map', default_value=default_map,
                              description='Full path to the saved map .yaml'),

        Node(package='nav2_map_server', executable='map_server', name='map_server',
             output='screen',
             parameters=[{'yaml_filename': LaunchConfiguration('map')}]),

        Node(package='nav2_amcl', executable='amcl', name='amcl', output='screen',
             parameters=[os.path.join(share, 'config', 'amcl.yaml')]),

        Node(package='nav2_lifecycle_manager', executable='lifecycle_manager',
             name='lifecycle_manager_localization', output='screen',
             parameters=[{'autostart': True,
                          'node_names': ['map_server', 'amcl']}]),
    ])
