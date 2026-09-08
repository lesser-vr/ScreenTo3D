import unittest
import numpy as np
from depthsbs_app.stereo import color_change, uniform_color_mask


class ExactMaskTests(unittest.TestCase):
    def test_color_change_all_byte_pairs(self):
        a, b = np.meshgrid(np.arange(256, dtype=np.uint8), np.arange(256, dtype=np.uint8))
        frame = np.stack((a, b, a), axis=2)
        previous = np.stack((b, a, a), axis=2)
        expected = np.max(np.abs(frame.astype(np.float32) - previous.astype(np.float32)), axis=2) / 255.0
        np.testing.assert_array_equal(color_change(frame, previous), expected)

    def test_background_thresholds_exact(self):
        rng = np.random.default_rng(25)
        frame = rng.integers(0, 256, (256, 256, 3), dtype=np.uint8)
        frame[:, 0] = np.arange(256, dtype=np.uint8)[:, None]
        for color in ((0, 255, 0), (127.5, 127.5, 127.5), (3.5, 190, 248.5)):
            color = np.asarray(color, np.float32)
            for tolerance in (0, .04, .5 / 255, 10.5 / 255, 1):
                expected = np.max(np.abs(frame.astype(np.float32) - color), axis=2) <= tolerance * 255
                np.testing.assert_array_equal(uniform_color_mask(frame, color, tolerance), expected)
