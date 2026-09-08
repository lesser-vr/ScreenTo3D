import unittest
from dataclasses import replace
import numpy as np
from depthsbs_app.stereo import project_eye, guide_depth, refine_flat_background
from depthsbs_app.pipeline import StereoSynthesizer
from depthsbs_app.config import MODES


class VisibilityTests(unittest.TestCase):
    def test_fractional_near_surface_does_not_leak_background(self):
        frame = np.zeros((3, 48, 3), np.uint8)
        frame[:] = (0, 255, 0)
        frame[:, 20:32] = (255, 0, 0)
        depth = np.zeros((3, 48), np.float32)
        depth[:, 20:32] = 1
        shift = np.full_like(depth, 2)
        shift[:, 20:32] = .51
        shift[:, 20] = .49
        for mirrored in (False, True):
            f, d, s = (frame[:, ::-1], depth[:, ::-1], -shift[:, ::-1]) if mirrored else (frame, depth, shift)
            old = project_eye(f, d, s)
            new = project_eye(f, d, s, conservative_coverage=True)
            x = 48 - 1 - 21 if mirrored else 21
            np.testing.assert_array_equal(old[0, x], (0, 255, 0))
            np.testing.assert_array_equal(new[0, x], (255, 0, 0))

    def test_coverage_preserves_integer_projection_and_empty_rows(self):
        rng = np.random.default_rng(19)
        frame = rng.integers(0, 256, (4, 32, 3), dtype=np.uint8)
        depth = rng.random((4, 32), dtype=np.float32)
        for amount in (0, -4, 4, 100):
            shift = np.full_like(depth, amount)
            np.testing.assert_array_equal(project_eye(frame, depth, shift),
                project_eye(frame, depth, shift, conservative_coverage=True))

    def test_fully_projected_out_rows_keep_original(self):
        frame = np.arange(3 * 8 * 3, dtype=np.uint8).reshape(3, 8, 3)
        depth = np.ones((3, 8), np.float32)
        shift = np.full_like(depth, 100)
        shift[1] = 0
        np.testing.assert_array_equal(project_eye(frame, depth, shift), frame)

    def test_equal_depth_collision_uses_higher_source_index(self):
        frame = np.arange(8 * 3, dtype=np.uint8).reshape(1, 8, 3)
        depth = np.ones((1, 8), np.float32)
        shift = -np.arange(8, dtype=np.float32)[None, :]
        expected = np.broadcast_to(frame[:, -1:], frame.shape)
        np.testing.assert_array_equal(project_eye(frame, depth, shift), expected)

    def test_zero_shift_identity(self):
        frame = np.arange(8 * 40 * 3, dtype=np.uint8).reshape(8, 40, 3)
        depth = np.zeros((8, 40), np.float32)
        np.testing.assert_array_equal(project_eye(frame, depth, depth), frame)

    def test_near_silhouette_wins_without_duplicate_or_foreground_fill(self):
        frame = np.zeros((8, 64, 3), np.uint8)
        frame[:] = (0, 255, 0)
        frame[:, 20:32] = (255, 0, 0)
        depth = np.zeros((8, 64), np.float32)
        depth[:, 20:32] = 1
        for shift in (-5, 5):
            output = project_eye(frame, depth, depth * shift)
            expected = frame.copy()
            expected[:] = (0, 255, 0)
            expected[:, 20 + shift:32 + shift] = (255, 0, 0)
            np.testing.assert_array_equal(output, expected)

    def test_projection_is_row_local_and_deterministic(self):
        frame = np.zeros((4, 16, 3), np.uint8)
        frame[0] = 50
        frame[1] = 100
        frame[2] = 150
        frame[3] = 200
        depth = np.ones((4, 16), np.float32)
        first = project_eye(frame, depth, depth * 3)
        np.testing.assert_array_equal(first, frame)
        np.testing.assert_array_equal(project_eye(frame, depth, depth * 3), first)

    def test_guide_constant_depth_finite(self):
        frame = np.zeros((20, 20, 3), np.uint8)
        depth = np.full((20, 20), .5, np.float32)
        np.testing.assert_allclose(guide_depth(frame, depth), depth, atol=1e-6)

    def test_flat_backdrop_is_color_independent_and_keeps_interior(self):
        for color in ((0, 255, 0), (255, 255, 255), (0, 0, 200)):
            frame = np.empty((100, 100, 3), np.uint8)
            frame[:] = color
            frame[20:80, 20:80] = (130, 40, 20)
            depth = np.zeros((100, 100), np.float32)
            depth[20:80, 20:80] = .8
            result = refine_flat_background(frame, depth, radius=2)
            np.testing.assert_allclose(result, depth, atol=1e-6)
            self.assertIsNot(result, depth)

    def test_nonuniform_border_bypasses_backdrop_heuristic(self):
        frame = np.zeros((40, 40, 3), np.uint8)
        frame[:, 20:] = 255
        depth = np.ones((40, 40), np.float32)
        self.assertIs(refine_flat_background(frame, depth), depth)


class TemporalBoundaryTests(unittest.TestCase):
    def test_scene_cut_forces_reset(self):
        renderer = StereoSynthesizer(32, 32, MODES['balanced'])
        depth = np.linspace(0, 1, 518 * 518, dtype=np.float32).reshape(1, 518, 518)
        renderer.render(np.zeros((32, 32, 3), np.uint8), depth)
        new = np.full((32, 32, 3), 255, np.uint8)
        self.assertTrue(renderer.is_scene_cut(new))
        output = renderer.render(new, depth[:, :, ::-1].copy())
        fresh = StereoSynthesizer(32, 32, MODES['balanced']).render(new, depth[:, :, ::-1].copy())
        np.testing.assert_array_equal(output, fresh)

    def test_changed_depth_does_not_leave_history_trail(self):
        policy = replace(MODES['balanced'], temporal_alpha=.1)
        renderer = StereoSynthesizer(32, 32, policy)
        frame = np.zeros((32, 32, 3), np.uint8)
        depth = np.zeros((1, 32, 32), np.float32)
        depth[:, :, 6:14] = 1
        renderer.render(frame, depth)
        moved = np.zeros_like(depth)
        moved[:, :, 20:28] = 1
        renderer.render(frame, moved)
        fresh = StereoSynthesizer(32, 32, policy)
        fresh.render(frame, moved)
        np.testing.assert_allclose(renderer.smoothed_depth, fresh.smoothed_depth, atol=1e-6)
