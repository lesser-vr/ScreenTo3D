import unittest
import numpy as np
from screento3d_app.temporal_blend import blend_depth


class TemporalBlendTests(unittest.TestCase):
    def test_threshold_has_no_jump(self):
        current = np.array([0.07999998, 0.0800001], np.float32)
        result = blend_depth(current, np.zeros(2, np.float32), False, 0.35, 0.08, 0.008)
        self.assertLess(float(np.ptp(result)), 2e-6)

    def test_motion_and_large_depth_refresh_exactly(self):
        current = np.array([0.01, 0.08, 0.09], np.float32)
        result = blend_depth(
            current,
            np.zeros(3, np.float32),
            np.array([True, False, False]),
            0.35,
            0.08,
            0.008,
        )
        np.testing.assert_array_equal(current, result)

    def test_small_motion_retains_ema(self):
        current = np.array([0.01, 0.04], np.float32)
        np.testing.assert_array_equal(
            blend_depth(current, np.zeros(2, np.float32), False, 0.35, 0.08, 0.008),
            current * np.float32(0.35),
        )
