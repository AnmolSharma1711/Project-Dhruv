"""Rewrite the Nav2 params file with launch-argument values (single source of truth)."""
import copy


def rewrite_params(params: dict, odom_topic: str, robot_radius: float) -> dict:
    p = copy.deepcopy(params)
    for node in ('bt_navigator', 'controller_server', 'velocity_smoother'):
        p[node]['ros__parameters']['odom_topic'] = odom_topic
    p['global_costmap']['global_costmap']['ros__parameters']['robot_radius'] = float(robot_radius)
    p['local_costmap']['local_costmap']['ros__parameters']['robot_radius'] = float(robot_radius)
    return p
