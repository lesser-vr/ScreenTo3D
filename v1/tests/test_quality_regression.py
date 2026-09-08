import unittest
import numpy as np
from compare_quality_regression import CONTRACT_SCHEMA, frame_metrics, validate_comparison_contract


class ComparisonMetricsTests(unittest.TestCase):
    def contract(self, kind='video'):
        path = dict(label='path', model='model', postprocessing='post', frame_generation='fg',
                    rates=dict(capture_hz=60, model_input_hz=30, fresh_depth_hz=30,
                               base_sbs_hz=30, generated_output_hz=60),
                    latency=dict(status='pending'))
        return dict(schema=CONTRACT_SCHEMA,
                    workload=dict(kind=kind, name='fixture', source_identity='sha256 fixture'),
                    environment=dict(gpu='gpu', driver='driver', display='display', power='power',
                                     competing_gpu_workloads='none'),
                    geometry=dict(input=[64, 32], per_eye=[64, 32], combined=[128, 32]),
                    paths=dict(baseline=dict(path), candidate=dict(path)),
                    review=dict(spatial_depth='pending', temporal_stability='pending',
                                occlusion_edges='pending', text='pending', cuts='pending',
                                binocular_consistency='pending', game_latency='not_applicable'))

    def test_eye_specific_change_and_temporal_spike_are_observable(self):
        before = np.zeros((2, 4, 3), np.uint8)
        after = before.copy()
        after[:, 2:] = 255
        metrics = frame_metrics(before, after, before, before)
        self.assertEqual(metrics['left_rgb_mae'], 0)
        self.assertEqual(metrics['right_rgb_mae'], 1)
        self.assertEqual(metrics['temporal_change_increase'], .5)

    def test_mismatched_geometry_is_not_compared(self):
        with self.assertRaises(ValueError):
            frame_metrics(np.zeros((2, 4, 3)), np.zeros((2, 6, 3)))
        for shape in ((0, 4, 3), (2, 0, 3), (2, 4, 1)):
            with self.subTest(shape=shape), self.assertRaises(ValueError):
                empty = np.zeros(shape, np.uint8)
                frame_metrics(empty, empty)

    def test_contract_records_distinct_rates_and_pending_review(self):
        result = validate_comparison_contract(self.contract(),
            dict(input=[64, 32], per_eye=[64, 32], combined=[128, 32]))
        self.assertEqual(result['paths']['baseline']['rates']['fresh_depth_hz'], 30)
        self.assertEqual(result['paths']['baseline']['rates']['generated_output_hz'], 60)
        self.assertFalse(result['comparison_ready'])

    def test_contract_rejects_geometry_and_rate_mislabeling(self):
        contract = self.contract()
        contract['geometry']['per_eye'] = [32, 32]
        with self.assertRaisesRegex(ValueError, 'geometry.per_eye'):
            validate_comparison_contract(contract,
                dict(input=[64, 32], per_eye=[64, 32], combined=[128, 32]))
        contract = self.contract()
        contract['paths']['candidate']['rates']['fresh_depth_hz'] = 61
        with self.assertRaisesRegex(ValueError, 'pipeline ordering'):
            validate_comparison_contract(contract,
                dict(input=[64, 32], per_eye=[64, 32], combined=[128, 32]))

    def test_game_contract_requires_latency_measurement_for_readiness(self):
        contract = self.contract('game')
        for key in contract['review']:
            contract['review'][key] = 'tie'
        result = validate_comparison_contract(contract,
            dict(input=[64, 32], per_eye=[64, 32], combined=[128, 32]))
        self.assertFalse(result['comparison_ready'])
        for path in contract['paths'].values():
            path['latency'] = dict(status='measured', method='camera', p50_ms=10, p95_ms=12, p99_ms=14)
        result = validate_comparison_contract(contract,
            dict(input=[64, 32], per_eye=[64, 32], combined=[128, 32]))
        self.assertTrue(result['comparison_ready'])

    def test_contract_rejects_unordered_latency_percentiles(self):
        contract = self.contract()
        contract['paths']['baseline']['latency'] = dict(
            status='measured', method='camera', p50_ms=12, p95_ms=10, p99_ms=14)
        with self.assertRaisesRegex(ValueError, 'percentiles'):
            validate_comparison_contract(contract,
                dict(input=[64, 32], per_eye=[64, 32], combined=[128, 32]))
