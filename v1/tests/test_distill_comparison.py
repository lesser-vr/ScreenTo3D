from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from compare_distill_small import oracle_error, save_rgb


class DistillComparisonTests(unittest.TestCase):
    def test_reference_gate_is_per_pixel(self):
        reference = np.ones((1, 4, 4), np.float32)
        self.assertTrue(oracle_error(reference, reference.copy())['passed'])
        actual = reference.copy()
        actual[0, 0, 0] += .01
        self.assertFalse(oracle_error(reference, actual)['passed'])

    def test_invalid_depth_rejected(self):
        reference = np.ones((1, 4, 4), np.float32)
        with self.assertRaises(ValueError):
            oracle_error(reference, reference * np.nan)
        with self.assertRaises(ValueError):
            oracle_error(reference, reference[:, :2])

    def test_review_write_failure_is_visible(self):
        with patch('compare_distill_small.cv2.imwrite', return_value=False):
            with self.assertRaises(RuntimeError):
                save_rgb(Path('unused.png'), np.zeros((4, 4, 3), np.uint8))


if __name__ == '__main__':
    unittest.main()
