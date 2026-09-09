import unittest

import numpy as np

from temporal_depth_experiment import MotionDepth, align_history


class MotionDepthTests(unittest.TestCase):
    def setUp(self):
        self.current = np.full((64, 96), .5, np.float32)
        self.gray = np.full((64, 96), 100, np.uint8)
        self.flow = np.zeros((64, 96, 2), np.float32)
        self.frame = np.repeat(self.gray[..., None], 3, axis=2)

    def test_static_history_blends_and_bounds_are_current(self):
        old = self.current + .01
        result, accepted = align_history(self.current, old, self.gray, self.gray, self.flow, self.flow)
        self.assertGreater(accepted.mean(), .9)
        self.assertGreater(result[20, 20], self.current[20, 20])
        np.testing.assert_array_equal(result[-1], self.current[-1])

    def test_disocclusion_and_photometric_failure_fall_back_exactly(self):
        forward = self.flow.copy()
        forward[..., 0] = 4
        result, mask = align_history(self.current, self.current+.01,
            self.gray, self.gray, forward, self.flow)
        self.assertFalse(mask.any())
        np.testing.assert_array_equal(result, self.current)
        result, mask = align_history(self.current, self.current+.01,
            self.gray, np.zeros_like(self.gray), self.flow, self.flow)
        self.assertFalse(mask.any())
        np.testing.assert_array_equal(result, self.current)

    def test_large_depth_disagreement_uses_current(self):
        result, mask = align_history(self.current, self.current+.2,
            self.gray, self.gray, self.flow, self.flow)
        self.assertFalse(mask.any())
        np.testing.assert_array_equal(result, self.current)

    def test_reset_identity_age_and_owned_raw_history(self):
        history = MotionDepth()
        result, stats = history.update(self.frame, self.current, 0, 0)
        self.assertEqual(stats['reset'], 'start')
        self.current[:] = .4
        self.assertTrue(np.all(history.previous == .5))
        _, stats = history.update(self.frame, self.current, 2, 16_666_667)
        self.assertEqual(stats['reset'], 'sequence_gap')
        _, stats = history.update(self.frame, self.current, 3, 100_000_000)
        self.assertEqual(stats['reset'], 'timestamp_discontinuity')
        _, stats = history.update(self.frame, self.current, 4, 116_666_667, cut=True)
        self.assertEqual(stats['reset'], 'cut')
        history.reset()
        self.assertIsNone(history.previous)

    def test_invalid_input_does_not_mutate_history(self):
        history = MotionDepth()
        history.update(self.frame, self.current, 0, 0)
        with self.assertRaises(ValueError):
            history.update(self.frame, self.current*np.nan, 1, 1)
        self.assertEqual(history.sequence, 0)

    def test_translated_object_reveals_current_background_without_trail(self):
        previous = self.current.copy()
        previous[16:48, 20:40] = .8
        current = self.current.copy()
        current[16:48, 24:44] = .8
        forward, backward = self.flow.copy(), self.flow.copy()
        forward[16:48, 20:40, 0] = 4
        backward[16:48, 24:44, 0] = -4
        result, accepted = align_history(current, previous, self.gray, self.gray, forward, backward)
        np.testing.assert_array_equal(result[16:48, 20:24], current[16:48, 20:24])
        self.assertFalse(accepted[16:48, 20:24].any())
        np.testing.assert_array_equal(result, current)

    def test_resize_and_automatic_cut_reset_exactly(self):
        history = MotionDepth()
        history.update(self.frame, self.current, 0, 0)
        result, stats = history.update(np.zeros_like(self.frame), self.current, 1, 16_666_667)
        self.assertEqual(stats['reset'], 'cut')
        np.testing.assert_array_equal(result, self.current)
        result, stats = history.update(self.frame[:, :64], self.current, 2, 33_333_334)
        self.assertEqual(stats['reset'], 'resize')
        np.testing.assert_array_equal(result, self.current)


if __name__ == '__main__':
    unittest.main()
