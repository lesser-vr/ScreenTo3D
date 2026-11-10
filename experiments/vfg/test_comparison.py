import unittest
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

from compare_desktop import ComparisonLive, LivePreview, comparison_mode, create_comparison, summarize


class ComparisonMetricsTests(unittest.TestCase):
    def test_model_routing_and_unknown_rejection_before_app_creation(self):
        self.assertEqual(comparison_mode('da2-small',False),'performance')
        self.assertEqual(comparison_mode('da2-small',True),'performance')
        self.assertEqual(comparison_mode('da2-base',False),'balanced')
        self.assertEqual(comparison_mode('da2-base',True),'balanced')
        with patch('compare_desktop.install') as install:
            with self.assertRaises(ValueError):
                create_comparison(None,True,'unknown')
            install.assert_not_called()
        with self.assertRaises(ValueError):
            comparison_mode('unknown',False)

    def test_vfg_reuses_each_models_input_path(self):
        from native_path import VfgRenderer, VfgOutputMixin, vfg_renderer, SUPPORTED_MODELS
        SmallVfgRenderer=vfg_renderer('da2-small')
        from depthsbs_app.live_small_gpu_input import LiveSmallGpuInput
        from depthsbs_app.live_source_gpu_candidate import LiveSourceGpuCandidate
        self.assertIs(SmallVfgRenderer.infer,LiveSmallGpuInput.infer)
        self.assertIs(SmallVfgRenderer._post,LiveSmallGpuInput._post)
        self.assertIs(VfgRenderer.infer,LiveSourceGpuCandidate.infer)
        for model in SUPPORTED_MODELS:
            renderer=vfg_renderer(model)
            self.assertEqual(renderer.expected_model,model)
            self.assertEqual(renderer.expected_layout,renderer.library_sha256)
            self.assertIs(renderer._project,VfgOutputMixin._project)

    def test_launcher_import_does_not_load_tensorrt(self):
        subprocess.run([sys.executable,'-c',
            "import sys; import compare_desktop; assert 'tensorrt' not in sys.modules; assert 'small_native' not in sys.modules"],
            check=True,creationflags=subprocess.CREATE_NO_WINDOW)

    def test_separates_generated_midpoint_from_original_and_oldest_age(self):
        # (Qt completion, output ID, due, source/midpoint, oldest, kind, base, ready, callback)
        samples = [(1_030_000_000, 1, 0, 1_000_000_000, 990_000_000, 1, 7, 0, 0),
                   (1_040_000_000, 2, 0, 1_010_000_000, 1_010_000_000, 0, 7, 0, 0),
                   (3_000_000_000, 3, 0, 0, 0, 0, 8, 0, 0)]
        result = summarize(samples, 1_000_000_000, 2_000_000_000, 1)
        self.assertEqual((result['output_fps'], result['original_fps'], result['generated_fps'], result['base_fps']), (2, 1, 1, 1))
        self.assertEqual(result['original_age_p50_ms'], 30)
        self.assertEqual(result['generated_midpoint_age_p50_ms'], 30)
        self.assertEqual(result['generated_oldest_age_p50_ms'], 40)

    def test_hidden_or_idle_window_has_no_fabricated_latency(self):
        result = summarize([], 1, 1_000_000_001, 0)
        self.assertEqual(result['output_fps'], 0)
        self.assertIsNone(result['original_age_p50_ms'])
        self.assertIsNone(result['generated_midpoint_age_p50_ms'])

    def test_normal_output_stays_excluded_and_marker_failure_fails_closed(self):
        live = SimpleNamespace(output_excluded=False)
        window = SimpleNamespace(winId=lambda: 123)
        with patch('depthsbs_app.capture_sources.mark_sbs_output', return_value=True), \
                patch('depthsbs_app.capture_sources.exclude_preview', return_value=True) as exclude:
            self.assertTrue(LivePreview.configureOutputCapture(live, window))
            self.assertTrue(live.output_excluded)
            exclude.assert_called_once_with(123)
        with patch('depthsbs_app.capture_sources.mark_sbs_output', return_value=False), \
                patch('depthsbs_app.capture_sources.exclude_preview') as exclude:
            self.assertFalse(LivePreview.configureOutputCapture(live, window))
            self.assertFalse(live.output_excluded)
            exclude.assert_not_called()
            self.assertFalse(ComparisonLive.configureOutputCapture(live, window))


if __name__ == '__main__':
    unittest.main()
