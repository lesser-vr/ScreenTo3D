import unittest
import numpy as np
from depthsbs_app.stereo_layout import dimensions, pack


class StereoLayoutTests(unittest.TestCase):
    def test_full_sbs_preserves_pixels_and_top_bottom_preserves_eyes(self):
        frame = np.arange(5 * 14 * 3, dtype=np.uint8).reshape(5, 14, 3)
        self.assertIs(pack(frame), frame)
        top_bottom = pack(frame, "full-tb")
        np.testing.assert_array_equal(top_bottom[:5], frame[:, :7])
        np.testing.assert_array_equal(top_bottom[5:], frame[:, 7:])

    def test_half_formats_average_with_independent_eye_edges(self):
        frame = np.zeros((3, 6, 3), dtype=np.uint8)
        frame[:, :3] = np.array([1, 2, 9], np.uint8)[None, :, None]
        frame[:, 3:] = 200
        result = pack(frame, "half-sbs")
        self.assertEqual(result.shape, (3, 4, 3))
        np.testing.assert_array_equal(result[0, :, 0], [2, 9, 200, 200])
        frame[0, :3] = 10
        frame[1, :3] = 11
        frame[2, :3] = 90
        result = pack(frame, "half-tb")
        np.testing.assert_array_equal(result[:, 0, 0], [11, 90, 200, 200])

    def test_all_shapes_and_rejection(self):
        for layout in ("full-sbs", "half-sbs", "full-tb", "half-tb"):
            for w, h in ((16, 16), (17, 19), (1920, 1080)):
                result = pack(np.zeros((h, w * 2, 3), np.uint8), layout)
                self.assertEqual(result.shape[1::-1], dimensions(w, h, layout))
        with self.assertRaises(ValueError):
            dimensions(1920, 1080, "auto")
