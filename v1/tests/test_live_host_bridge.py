import unittest

import cv2
import numpy as np

from depthsbs_app.live_host_bridge import capture_rgb, publish_rgb


class HostBridgeTests(unittest.TestCase):
    def test_capture_exact_owned_and_source_unchanged(self):
        rng = np.random.default_rng(928)
        for width, height in ((16, 16), (127, 69), (1920, 1080)):
            source = rng.integers(0, 256, (height, width, 4), np.uint8)
            original = source.copy()
            result = capture_rgb(source, width, height)
            np.testing.assert_array_equal(
                result, cv2.cvtColor(original, cv2.COLOR_BGRA2RGB)
            )
            np.testing.assert_array_equal(source, original)
            self.assertFalse(np.shares_memory(result, source))
            source.fill(0)
            np.testing.assert_array_equal(
                result, cv2.cvtColor(original, cv2.COLOR_BGRA2RGB)
            )

    def test_publish_exact_alpha_bounds_and_owned_input(self):
        rng = np.random.default_rng(929)
        for width, height in ((32, 16), (254, 69), (3840, 1080)):
            frame = rng.integers(0, 256, (height, width, 3), np.uint8)
            original = frame.copy()
            storage = np.full(height * width * 4 + 64, 73, np.uint8)
            publish_rgb(storage, frame)
            expected = cv2.cvtColor(frame, cv2.COLOR_RGB2BGRA)
            np.testing.assert_array_equal(
                storage[:-64].reshape(expected.shape), expected
            )
            self.assertTrue(np.all(storage[-64:] == 73))
            np.testing.assert_array_equal(frame, original)
            frame.fill(0)
            np.testing.assert_array_equal(
                storage[:-64].reshape(expected.shape), expected
            )


if __name__ == "__main__":
    unittest.main()
