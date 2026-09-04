import unittest
from depthsbs_app.telemetry import StageMetrics


class TelemetryTests(unittest.TestCase):
    def test_window_and_lifetime(self):
        metrics = StageMetrics(2)
        for value in (1, 2, 3):
            metrics.observe('depth', value)
        stage = metrics.summary()['depth']
        self.assertEqual(stage['count'], 3)
        self.assertEqual(stage['sample_count'], 2)
        self.assertEqual(stage['mean_ms'], 2000)
        self.assertEqual(stage['p50_ms'], 2500)
        self.assertEqual(stage['p95_ms'], 2950)
        self.assertEqual(stage['p99_ms'], 2990)
        self.assertEqual(stage['max_ms'], 3000)

    def test_empty_single_and_invalid(self):
        metrics = StageMetrics()
        self.assertEqual(metrics.summary(), {})
        metrics.observe('one', 0)
        self.assertEqual(metrics.summary()['one']['p99_ms'], 0)
        for value in (-1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                metrics.observe('bad', value)
        with self.assertRaises(ValueError):
            StageMetrics(0)

    def test_exception_is_timed(self):
        metrics = StageMetrics()
        with self.assertRaises(RuntimeError):
            with metrics.measure('failure'):
                raise RuntimeError('test')
        self.assertEqual(metrics.summary()['failure']['count'], 1)
