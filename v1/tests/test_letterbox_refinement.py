import unittest
import numpy as np

from screento3d_app.stereo import refine_flat_background
from letterbox_refinement import detect_content, refine_padding_background, restore_padding


class PaddingRefinementTests(unittest.TestCase):
    def fixture(self, horizontal=False):
        frame = np.full((100, 120, 3), (0, 240, 0), np.uint8)
        frame[25:75, 40:80] = (120, 50, 30)
        if horizontal:
            frame[:6] = 0
            frame[-6:] = 0
        else:
            frame[:, :6] = 0
            frame[:, -6:] = 0
        depth = np.linspace(0, 1, 12000, dtype=np.float32).reshape(100, 120)
        return frame, depth

    def test_both_axes_refine_only_interior_without_mutation(self):
        for horizontal in (False, True):
            frame, depth = self.fixture(horizontal)
            original_frame, original_depth = frame.copy(), depth.copy()
            region = detect_content(frame)
            self.assertIsNotNone(region)
            self.assertIs(refine_flat_background(frame, depth), depth)
            result = refine_padding_background(frame, depth)
            self.assertIsNot(result, depth)
            outside = np.ones(depth.shape, bool)
            outside[region.iy0:region.iy1, region.ix0:region.ix1] = False
            np.testing.assert_array_equal(result[outside], depth[outside])
            np.testing.assert_array_equal(frame, original_frame)
            np.testing.assert_array_equal(depth, original_depth)
            self.assertTrue(np.isfinite(result).all())

    def test_no_padding_retains_existing_behavior(self):
        frame, depth = self.fixture()
        frame[:, :6] = frame[:, -6:] = (0, 240, 0)
        self.assertIsNone(detect_content(frame))
        np.testing.assert_array_equal(refine_padding_background(frame, depth), refine_flat_background(frame, depth))

    def test_single_asymmetric_oversized_and_captioned_bars_rejected(self):
        for kind in ('single', 'asymmetric', 'oversized', 'caption'):
            frame, depth = self.fixture()
            if kind == 'single':
                frame[:, -6:] = (0, 240, 0)
            elif kind == 'asymmetric':
                frame[:, :10] = 0
            elif kind == 'oversized':
                frame[:, :20] = frame[:, -20:] = 0
            else:
                frame[50, 1] = 255
            self.assertIsNone(detect_content(frame), kind)
            self.assertIs(refine_padding_background(frame, depth), depth)

    def test_dark_scene_and_textured_inner_border_bypass(self):
        frame, depth = self.fixture()
        self.assertIsNone(detect_content(np.zeros_like(frame)))
        rng = np.random.default_rng(191)
        frame[:, 6:-6] = rng.integers(20, 256, frame[:, 6:-6].shape, dtype=np.uint8)
        self.assertIs(refine_padding_background(frame, depth), depth)

    def test_restore_exact_padding_and_preserve_content_both_eyes(self):
        for horizontal in (False, True):
            source, _ = self.fixture(horizontal)
            region = detect_content(source)
            stereo = np.full((100, 240, 3), 117, np.uint8)
            result = restore_padding(stereo, source, region)
            for eye in (result[:, :120], result[:, 120:]):
                mask = np.ones(source.shape[:2], bool)
                mask[region.y0:region.y1, region.x0:region.x1] = False
                np.testing.assert_array_equal(eye[mask], source[mask])
                self.assertTrue(np.all(eye[~mask] == 117))
            self.assertTrue(np.all(stereo == 117))
        self.assertIs(restore_padding(stereo, source, None), stereo)

    def test_two_axis_windowbox_is_bounded(self):
        frame, depth = self.fixture()
        frame[:6] = frame[-6:] = 0
        region = detect_content(frame)
        self.assertEqual((region.x0, region.y0, region.x1, region.y1), (6, 6, 114, 94))
        self.assertIsNot(refine_padding_background(frame, depth), depth)
