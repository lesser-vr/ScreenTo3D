import unittest

import numpy as np

from compare_small_aspect import comparison, preprocess
from depthsbs_app.pipeline import preprocess as current_preprocess


class SmallAspectTests(unittest.TestCase):
    def test_square_preprocessing_preserves_current_values(self):
        frame = np.random.default_rng(42).integers(0, 256, (360, 640, 3), dtype=np.uint8)
        actual = preprocess(frame, (518, 518))
        np.testing.assert_array_equal(actual, current_preprocess(frame))
        self.assertTrue(actual.flags.c_contiguous)

    def test_rectangular_shape_and_rejection(self):
        frame = np.zeros((360, 640, 3), np.uint8)
        self.assertEqual(preprocess(frame, (392, 700)).shape, (1, 3, 392, 700))
        with self.assertRaises(ValueError):
            preprocess(frame, (392, 686))
        with self.assertRaises(ValueError):
            preprocess(frame.astype(np.float32), (392, 700))

    def test_oracle_gate(self):
        reference = np.arange(1, 101, dtype=np.float32).reshape(1, 10, 10)
        self.assertTrue(comparison(reference, reference.copy())['passed'])
        self.assertFalse(comparison(reference, reference + 1)['passed'])
        with self.assertRaises(ValueError):
            comparison(reference, reference * np.nan)


if __name__ == '__main__':
    unittest.main()
