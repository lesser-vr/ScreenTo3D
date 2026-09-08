import unittest
import numpy as np
from depthsbs_app.stereo import project_eye, refine_flat_background
from depthsbs_app.pipeline import StereoSynthesizer
from depthsbs_app.config import MODES
from quality_scenes import motion_frame


def scalar_projection(frame, depth, shift):
    """Small independent visibility oracle, including farther-side hole fill."""
    height, width = depth.shape
    result = frame.copy()
    for y in range(height):
        winners = {}
        for x in range(width):
            priority = (int(np.float32(np.clip(depth[y, x], 0, 1)) * np.float32(65535)) + 1, x)
            target = x + float(shift[y, x])
            for column in {int(np.floor(target)), int(np.ceil(target))}:
                if 0 <= column < width and (column not in winners or priority > winners[column]):
                    winners[column] = priority
        for column in range(width):
            if not winners:
                continue
            owner = winners.get(column)
            if owner is None:
                left = max((p for p in winners if p < column), default=None)
                right = min((p for p in winners if p > column), default=None)
                chosen = right if left is None else left if right is None or winners[left][0] <= winners[right][0] else right
                owner = winners[chosen]
            result[y, column] = frame[y, owner[1]]
    return result


class MotionQualityTests(unittest.TestCase):
    def test_textured_occlusion_matches_scalar_oracle(self):
        rng = np.random.default_rng(20260904)
        for _ in range(12):
            frame = rng.integers(0, 256, (5, 32, 3), dtype=np.uint8)
            depth = rng.choice(np.array([0, .2, .5, 1], np.float32), (5, 32))
            shift = rng.uniform(-40, 40, (5, 32)).astype(np.float32)
            for sign in (-1, 1):
                np.testing.assert_array_equal(project_eye(frame, depth, shift * sign, True),
                                              scalar_projection(frame, depth, shift * sign))

    def test_textured_scene_bypasses_flat_background(self):
        for index in (0, 12, 24, 25, 47):
            frame, depth = motion_frame(index)
            self.assertIs(refine_flat_background(frame, depth), depth)

    def test_fast_motion_rejects_stale_depth_all_policies(self):
        # Fresh known depth per frame isolates temporal blending, not cadence.
        for policy in MODES.values():
            renderer = StereoSynthesizer(160, 96, policy)
            for index in (0, 2, 4, 6, 24, 25, 26):
                frame, depth = motion_frame(index, 160, 96)
                renderer.render(frame, depth[None])
                expected = np.clip((depth - .1) / .8, 0, 1)
                np.testing.assert_allclose(renderer.smoothed_depth, expected, atol=1e-6)
            self.assertEqual(renderer.flat_background_frames, 0)

    def test_off_cadence_cut_matches_fresh_renderer(self):
        for policy in MODES.values():
            renderer = StereoSynthesizer(160, 96, policy)
            before, depth = motion_frame(24, 160, 96)
            renderer.render(before, depth[None])
            after, depth = motion_frame(25, 160, 96)
            self.assertTrue(renderer.is_scene_cut(after))
            actual = renderer.render(after, depth[None])
            expected = StereoSynthesizer(160, 96, policy).render(after, depth[None])
            np.testing.assert_array_equal(actual, expected)
