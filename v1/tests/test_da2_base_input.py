import unittest
import numpy as np
from da2_base_experiment import validate_frame


class Da2BaseInputTests(unittest.TestCase):
    def test_rgb_and_aspect_bounds(self):
        validate_frame(np.zeros((608, 1056, 3), np.uint8))
        for frame in (None, np.zeros((16, 16), np.uint8), np.zeros((16, 16, 4), np.uint8),
                      np.zeros((16, 16, 3), np.float32), np.zeros((16, 100, 3), np.uint8),
                      np.zeros((15, 16, 3), np.uint8), np.zeros((1921, 1921, 3), np.uint8)):
            with self.subTest(shape=getattr(frame, 'shape', None)), self.assertRaises(ValueError):
                validate_frame(frame)
