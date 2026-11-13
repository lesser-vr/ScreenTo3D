import unittest
from dataclasses import replace
import numpy as np
from screento3d_app.config import MODES
from screento3d_app.pipeline import depth_refresh_reason


class LocalMotionTests(unittest.TestCase):
    def test_small_region_at_edges_and_window_boundaries(self):
        reference = np.full((96, 160, 3), 40, np.uint8)
        for y, x in ((0, 0), (92, 156), (15, 15), (31, 63), (48, 80)):
            current = reference.copy()
            current[y:y+4, x:x+4] = 48
            self.assertEqual(depth_refresh_reason(current, reference, 1, MODES['performance'], False), 'local_motion')
            old = replace(MODES['performance'], local_motion_window=0)
            self.assertEqual(depth_refresh_reason(current, reference, 1, old, False), 'reuse')

    def test_low_level_noise_and_uniform_brightness_do_not_trigger_local_guard(self):
        reference = np.full((96, 160, 3), 80, np.uint8)
        rng = np.random.default_rng(178)
        for delta in (2, 4, 8):
            uniform = reference + delta
            self.assertEqual(depth_refresh_reason(uniform, reference, 1, MODES['performance'], False), 'reuse')
            for _ in range(8):
                noisy = (reference.astype(int) + rng.integers(-delta, delta+1, reference.shape)).astype(np.uint8)
                self.assertEqual(depth_refresh_reason(noisy, reference, 1, MODES['performance'], False), 'reuse')

    def test_isolated_pixel_noise_remains_below_local_area(self):
        reference = np.full((96, 160, 3), 40, np.uint8)
        current = reference.copy()
        current[::32, ::32] = 255
        self.assertEqual(depth_refresh_reason(current, reference, 1, MODES['performance'], False), 'reuse')
