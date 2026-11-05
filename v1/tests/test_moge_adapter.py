"""Run in the isolated MoGe experiment environment."""
import unittest
import numpy as np
from evaluate_moge_small import inverse_depth


class MogeAdapterTests(unittest.TestCase):
    def test_invalid_geometry_is_finite_far_depth(self):
        depth = np.array([[2., np.inf, -1., np.nan]], dtype=np.float32)
        result, coverage = inverse_depth(depth, np.ones_like(depth, dtype=bool))
        np.testing.assert_array_equal(result, [[[.5, 0., 0., 0.]]])
        self.assertEqual(coverage, .25)

    def test_mask_and_near_far_polarity(self):
        depth = np.array([[1., 2., 3.]], dtype=np.float32)
        result, _ = inverse_depth(depth, np.array([[True, True, False]]))
        np.testing.assert_array_equal(result, [[[1., .5, 0.]]])

    def test_empty_mask_rejected(self):
        with self.assertRaises(ValueError):
            inverse_depth(np.ones((2, 2), dtype=np.float32), np.zeros((2, 2), dtype=bool))
