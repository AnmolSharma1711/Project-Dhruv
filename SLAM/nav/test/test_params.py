import os
import unittest

import yaml

from nav.params_util import rewrite_params

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, '..', 'config')
RAW = open(os.path.join(CFG, 'nav2_params.yaml'), 'rb').read()
P = yaml.safe_load(RAW.decode('utf-8'))


def cs(p):
    return p['controller_server']['ros__parameters']


class Params(unittest.TestCase):
    def test_no_conflict_markers_or_bom(self):
        for marker in (b'<<<<<<<', b'>>>>>>>', b'\n=======\n'):
            self.assertNotIn(marker, RAW)
        self.assertFalse(RAW.startswith(b'\xef\xbb\xbf'))

    def test_odom_topic_everywhere(self):
        for n in ('bt_navigator', 'controller_server', 'velocity_smoother'):
            self.assertIn('odom_topic', P[n]['ros__parameters'], n)

    def test_controller(self):
        f = cs(P)['FollowPath']
        self.assertTrue(f['use_rotate_to_heading'])
        self.assertFalse(f['allow_reversing'])
        self.assertLessEqual(f['desired_linear_vel'], 0.148)
        self.assertGreaterEqual(f['rotate_to_heading_angular_vel'], 0.32)   # above deadband

    def test_spin_enabled(self):
        b = P['behavior_server']['ros__parameters']
        self.assertIn('spin', b['behavior_plugins'])
        self.assertGreaterEqual(b['min_rotational_vel'], 0.32)
        self.assertEqual(b['global_frame'], 'odom')

    def test_planner(self):
        g = P['planner_server']['ros__parameters']['GridBased']
        self.assertFalse(g['allow_unknown'])
        self.assertTrue(g['use_astar'])

    def test_no_sideways(self):
        v = P['velocity_smoother']['ros__parameters']
        self.assertEqual(v['max_velocity'][1], 0.0)
        self.assertEqual(v['min_velocity'][1], 0.0)
        self.assertLessEqual(v['max_velocity'][0], 0.148)

    def test_inflation_margin(self):
        for c, k in (('global_costmap', 'global_costmap'), ('local_costmap', 'local_costmap')):
            p = P[c][k]['ros__parameters']
            self.assertGreaterEqual(p['inflation_layer']['inflation_radius'],
                                    p['robot_radius'] + 0.10)
        self.assertNotIn('voxel_layer', P['local_costmap']['local_costmap']['ros__parameters']['plugins'])

    def test_rewrite(self):
        q = rewrite_params(P, '/my/odom', 0.2)
        self.assertEqual(q['controller_server']['ros__parameters']['odom_topic'], '/my/odom')
        self.assertEqual(q['bt_navigator']['ros__parameters']['odom_topic'], '/my/odom')
        self.assertEqual(q['global_costmap']['global_costmap']['ros__parameters']['robot_radius'], 0.2)
        self.assertEqual(q['local_costmap']['local_costmap']['ros__parameters']['robot_radius'], 0.2)
        self.assertEqual(P['controller_server']['ros__parameters']['odom_topic'], '/odometry/filtered')

    def test_bridge_yaml(self):
        b = yaml.safe_load(open(os.path.join(CFG, 'bridge.yaml')))['cmd_vel_bridge']['ros__parameters']
        self.assertAlmostEqual(b['pwm_per_mps'], 180 / 0.148, delta=1)
        self.assertAlmostEqual(b['pwm_per_radps'], 180 / (2 * 3.14159265 / 2.75), delta=0.5)
        self.assertEqual(b['max_pwm'], 180)


if __name__ == '__main__':
    unittest.main()
