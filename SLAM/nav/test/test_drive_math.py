import math
import unittest

from nav.drive_math import format_mix, sanitize, to_power, twist_to_mix

K_L, K_W, MINP, MAXP = 1216.0, 78.8, 25, 180


def mix(vx, wz, ds=1, ts=1):
    return twist_to_mix(vx, wz, K_L, K_W, MINP, MAXP, ds, ts)


class DriveMath(unittest.TestCase):
    def test_top_speed(self):
        self.assertAlmostEqual(mix(0.14, 0)[0], 170, delta=1)
        self.assertAlmostEqual(mix(-0.14, 0)[0], -170, delta=1)

    def test_deadband_raises_small_commands(self):
        self.assertEqual(mix(0.02, 0)[0], 25)        # 24.3 -> 25
        self.assertEqual(mix(0, 0.1)[2], 25)         # 7.9  -> 25
        self.assertEqual(mix(0, -0.1)[2], -25)

    def test_zero(self):
        self.assertEqual(mix(0, 0), (0, 0, 0))
        self.assertEqual(mix(0.0005, 0.0005), (0, 0, 0))

    def test_turn(self):
        self.assertAlmostEqual(mix(0, 0.5)[2], 39, delta=1)

    def test_never_above_cap(self):
        for v in (0.3, 1.0, 50.0):
            self.assertLessEqual(abs(mix(v, v)[0]), 180)
            self.assertLessEqual(abs(mix(v, v)[2]), 180)

    def test_sideways_always_zero(self):
        for vx in (-0.14, 0, 0.14):
            self.assertEqual(mix(vx, 0.3)[1], 0)

    def test_nan_inf_none(self):
        for bad in (float('nan'), float('inf'), -float('inf'), None, 'x'):
            self.assertEqual(sanitize(bad), 0.0)
            self.assertEqual(mix(bad, bad), (0, 0, 0))

    def test_signs(self):
        self.assertEqual(mix(0.14, 0.5, ds=-1, ts=-1)[0], -mix(0.14, 0.5)[0])
        self.assertEqual(mix(0.14, 0.5, ds=-1, ts=-1)[2], -mix(0.14, 0.5)[2])

    def test_format(self):
        self.assertEqual(format_mix(170, 0, -39), '<MIX,170,0,-39>')


if __name__ == '__main__':
    unittest.main()
