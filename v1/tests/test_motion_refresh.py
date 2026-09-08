import unittest
from dataclasses import replace
from unittest.mock import patch
import numpy as np
from depthsbs_app.pipeline import depth_refresh_reason, StereoSynthesizer
from depthsbs_app.config import MODES
from quality_scenes import motion_frame


class MotionRefreshTests(unittest.TestCase):
    def test_static_reuses_and_small_noise_does_not_refresh(self):
        frame, _ = motion_frame(0)
        policy = MODES['performance']
        self.assertEqual(depth_refresh_reason(frame, frame, 1, policy, False), 'reuse')
        noisy = np.clip(frame.astype(int) + 2, 0, 255).astype(np.uint8)
        self.assertEqual(depth_refresh_reason(noisy, frame, 1, policy, False), 'reuse')

    def test_motion_refresh_matches_fresh_depth_not_stale(self):
        first, old_depth = motion_frame(0, 160, 96)
        moved, new_depth = motion_frame(1, 160, 96)
        policy = MODES['performance']
        self.assertEqual(depth_refresh_reason(moved, first, 1, policy, False), 'motion')
        renderer = StereoSynthesizer(160, 96, policy)
        renderer.render(first, old_depth[None])
        output = renderer.render(moved, new_depth[None])
        fresh = StereoSynthesizer(160, 96, policy).render(moved, new_depth[None])
        np.testing.assert_array_equal(output, fresh)
        stale = StereoSynthesizer(160, 96, policy).render(moved, old_depth[None])
        self.assertFalse(np.array_equal(stale, fresh))

    def test_cut_and_cadence_skip_motion_work(self):
        frame, _ = motion_frame(0)
        for index, cut, reason in ((0, False, 'cadence'), (1, True, 'cut')):
            with patch('depthsbs_app.pipeline.color_change', side_effect=AssertionError('unexpected scan')):
                self.assertEqual(depth_refresh_reason(frame, frame, index, MODES['performance'], cut), reason)
        self.assertEqual(depth_refresh_reason(frame, None, 0, MODES['performance'], False), 'initial')

    def test_reference_must_be_last_inferred_frame(self):
        policy = replace(MODES['performance'], inference_cadence=4, local_motion_window=0)
        original = np.zeros((100, 100, 3), np.uint8)
        first = original.copy()
        first[:1, :60] = 255  # .6%, allowed to reuse
        second = first.copy()
        second[1:2, :60] = 255  # 1.2% cumulative, must refresh
        self.assertEqual(depth_refresh_reason(first, original, 1, policy, False), 'reuse')
        self.assertEqual(depth_refresh_reason(second, original, 2, policy, False), 'motion')

    def test_below_and_at_area_threshold(self):
        policy = replace(MODES['performance'], local_motion_window=0)
        reference = np.zeros((100, 100, 3), np.uint8)
        current = reference.copy()
        current.reshape(-1, 3)[:99] = 255
        self.assertEqual(depth_refresh_reason(current, reference, 1, policy, False), 'reuse')
        current.reshape(-1, 3)[99] = 255
        self.assertEqual(depth_refresh_reason(current, reference, 1, policy, False), 'motion')
