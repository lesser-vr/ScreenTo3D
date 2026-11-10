import unittest

import numpy as np

from depthsbs_app.stereo_stability import ScreenPlane, DepthRangeClock, sample_depth


class DepthRangeClockTests(unittest.TestCase):
    def test_uses_source_time_not_processing_rate_and_resets_discontinuities(self):
        clock = DepthRangeClock()
        self.assertTrue(clock.update(1_000_000_000)[1])
        self.assertEqual(clock.update(1_025_000_000),(.025,False))
        self.assertEqual(clock.update(1_125_000_000),(.1,False))
        for stamp in (1_125_000_000,1_124_000_000,2_000_000_000):
            dt,reset = clock.update(stamp)
            self.assertTrue(reset)
            self.assertGreater(dt,0)
            self.assertLessEqual(dt,.1)
        self.assertTrue(clock.update(2_016_000_000,reset=True)[1])

    def test_invalid_stamps_fail_without_mutating_history(self):
        clock=DepthRangeClock()
        clock.update(100)
        for value in (0,-1,1.5,True):
            with self.assertRaises(ValueError): clock.update(value)
            self.assertEqual(clock.source_ns,100)
        self.assertTrue(clock.update(None)[1])
        self.assertEqual(clock.update(None),(1/60,False))


class ScreenPlaneTests(unittest.TestCase):
    def test_static_inference_jitter_does_not_move_screen_plane(self):
        tracker = ScreenPlane()
        self.assertAlmostEqual(tracker.update(np.full((32, 32), .6)), .6)
        for depth in (.61, .585, .62, .59):
            self.assertAlmostEqual(tracker.update(np.full((32, 32), depth)), .6)

    def test_moving_target_is_rate_limited_and_cut_reanchors(self):
        tracker = ScreenPlane()
        tracker.update(np.full((32, 32), .3), 1_000_000_000)
        for i in range(1, 31):
            prior = tracker.value
            tracker.update(np.full((32, 32), .8), 1_000_000_000 + i * 33_333_333)
            self.assertLessEqual(abs(tracker.value - prior), .002000001)
        self.assertLess(tracker.value, .361)
        self.assertEqual(tracker.update(np.ones((32, 32)), 2_100_000_000, reset=True), .8)

    def test_content_outside_center_cannot_pull_anchor(self):
        samples = np.zeros((32, 32), np.float32)
        samples[8:24, 8:24] = .6
        first = ScreenPlane().update(samples)
        samples[:8] = 1
        self.assertEqual(ScreenPlane().update(samples), first)

    def test_invalid_input_rejected_and_samples_cover_tiny_source(self):
        with self.assertRaises(ValueError):
            ScreenPlane().update(np.full((32, 32), np.nan))
        with self.assertRaises(ValueError):
            ScreenPlane().update(np.zeros((32, 32)), -1)
        depth = np.arange(16 * 17, dtype=np.float32).reshape(16, 17)
        self.assertEqual(sample_depth(depth).shape, (32, 32))
        self.assertEqual(sample_depth(depth)[0, 0], depth[0, 0])
        self.assertEqual(sample_depth(depth)[-1, -1], depth[-1, -1])
