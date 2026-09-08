import unittest
import numpy as np
from temporal_diagnostics import aligned_change, TemporalProbe


class TemporalDiagnosticTests(unittest.TestCase):
    def test_known_translation(self):
        rng = np.random.default_rng(42)
        rgb = rng.integers(0, 255, (64, 96, 3), dtype=np.uint8)
        depth = rng.random((64, 96), dtype=np.float32)
        moved = np.roll(rgb, 3, axis=1)
        changed = np.roll(depth, 3, axis=1)
        forward = np.zeros((64, 96, 2), np.float32); forward[..., 0] = 3
        result = aligned_change(rgb, moved, depth, changed, -forward, forward)
        self.assertGreater(result['valid_fraction'], .8)
        self.assertLess(result['aligned_mae'], 1e-6)
        self.assertGreater(result['unaligned_mae'], .1)
        result = aligned_change(rgb, moved, depth, changed+.1, -forward, forward)
        self.assertAlmostEqual(result['aligned_mae'], .1, places=5)

    def test_inconsistent_flow_and_occlusion(self):
        rgb = np.zeros((32, 48, 3), np.uint8)
        d = np.zeros((32, 48), np.float32)
        flow = np.zeros((32, 48, 2), np.float32)
        result = aligned_change(rgb, rgb+255, d, d, flow, flow)
        self.assertIsNone(result['aligned_mae'])
        result = aligned_change(rgb, rgb, d, d, flow+4, flow+4)
        self.assertEqual(result['valid_fraction'], 0)

    def test_actual_flow_static_and_cut(self):
        rng = np.random.default_rng(1)
        rgb = rng.integers(0, 255, (64, 96, 3), dtype=np.uint8)
        d = rng.random((1, 64, 96), dtype=np.float32)
        probe = TemporalProbe()
        probe.add(rgb, d); probe.add(rgb, d)
        self.assertLess(probe.rows[-1]['aligned_mae'], .001)
        probe.add(rgb, d, cut=True)
        self.assertEqual(probe.rows[-1]['excluded_reason'], 'scene_cut')
        self.assertNotIn('aligned_mae', probe.rows[-1])
        probe.add(rgb, d)
        self.assertLess(probe.rows[-1]['aligned_mae'], .001)
        self.assertIsNotNone(probe.report()['summary']['aligned_mae'])

    def test_invalid_and_bounded(self):
        rgb = np.zeros((32, 48, 3), np.uint8)
        probe = TemporalProbe()
        with self.assertRaises(ValueError): probe.add(rgb, np.full((1, 32, 48), np.nan))
        probe.rows = [{}]*124
        with self.assertRaises(ValueError): probe.add(rgb, np.zeros((1, 32, 48)))
