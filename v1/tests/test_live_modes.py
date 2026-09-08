import unittest
import numpy as np
from depthsbs_app.config import MODES
from depthsbs_app.live_policy import (
    LIVE_MODES,
    resolve_live,
    refresh_live as depth_refresh_reason,
)


class LiveModeTests(unittest.TestCase):
    def test_only_live_modes(self):
        self.assertEqual(set(LIVE_MODES), {"performance", "balanced", "video-quality"})
        for name in ("offline-quality", "unknown"):
            with self.assertRaises(ValueError):
                resolve_live(name)

    def test_file_defaults_unchanged(self):
        self.assertTrue(MODES["performance"].flat_background_refinement)
        self.assertFalse(resolve_live("performance").flat_background_refinement)
        self.assertEqual(resolve_live("video-quality").depth_guide_radius, 12)
        self.assertEqual(MODES["balanced"].temporal_depth_transition, 0)
        self.assertEqual(resolve_live("balanced").temporal_depth_transition, 0.008)

    def test_cadence_never_reuses_after_reset_or_cut(self):
        frame = np.zeros((32, 32, 3), np.uint8)
        policy = resolve_live("performance")
        self.assertEqual(depth_refresh_reason(frame, None, 1, policy, False), "initial")
        self.assertEqual(depth_refresh_reason(frame, frame, 1, policy, True), "cut")
        self.assertEqual(depth_refresh_reason(frame, frame, 1, policy, False), "reuse")
        self.assertNotEqual(
            depth_refresh_reason(frame + 255, frame, 1, policy, False), "reuse"
        )
        one_pixel = frame.copy()
        one_pixel[0, 0, 0] = 1
        self.assertEqual(
            depth_refresh_reason(one_pixel, frame, 1, policy, False), "motion"
        )

    def test_combined_percentiles_exact(self):
        rng = np.random.default_rng(22)
        for shape in ((32, 32), (518, 518), (1080, 1920)):
            array = rng.random(shape, dtype=np.float32)
            old = [float(np.percentile(array, q)) for q in (2.0, 98.0)]
            self.assertEqual(
                old,
                list(map(float, np.percentile(array, [2.0, 98.0]).astype(array.dtype))),
            )
