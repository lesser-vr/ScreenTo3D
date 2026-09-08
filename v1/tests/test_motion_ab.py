import unittest
from compare_motion_refresh import synthetic_results


class MotionComparisonTests(unittest.TestCase):
    def test_large_motion_benefit_without_static_extra_work(self):
        results = {(r['case'], r['enabled']): r for r in synthetic_results()}
        self.assertEqual(results['fast', False]['stale_depth_frames'], 12)
        self.assertEqual(results['fast', True]['stale_depth_frames'], 0)
        for enabled in (False, True):
            self.assertEqual(results['static', enabled]['inferences'], 12)
            self.assertEqual(results['static', enabled]['stale_depth_frames'], 0)

    def test_small_and_low_contrast_refresh_avoids_stale_depth(self):
        results = {(r['case'], r['enabled']): r for r in synthetic_results()}
        for case in ('small', 'low_contrast'):
            self.assertEqual(results[case, False]['stale_depth_frames'], 12)
            self.assertEqual(results[case, True]['stale_depth_frames'], 0)
            self.assertEqual(results[case, True]['inferences'], 24)
