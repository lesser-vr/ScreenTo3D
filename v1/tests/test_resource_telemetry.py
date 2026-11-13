import unittest
from unittest.mock import Mock, patch

import numpy as np

from screento3d_app.resource_telemetry import ResourceMetrics
from screento3d_app import trt_backend as backend


class ResourceMetricsTests(unittest.TestCase):
    def test_throttle_and_aggregate(self):
        metrics = ResourceMetrics()
        query = Mock(side_effect=[(80, 100), (40, 100), (70, 100)])
        metrics.sample_memory(query, now=0)
        metrics.sample_memory(query, now=.5)
        metrics.sample_memory(query, now=1)
        metrics.sample_memory(query, now=1.1, force=True)
        memory = metrics.summary()['device_memory']
        self.assertEqual(query.call_count, 3)
        self.assertEqual(memory['sample_count'], 3)
        self.assertEqual(memory['first_used_bytes'], 20)
        self.assertEqual(memory['last_used_bytes'], 30)
        self.assertEqual(memory['sampled_max_used_bytes'], 60)

    def test_unavailable_is_not_zero_and_recovers(self):
        metrics = ResourceMetrics()
        metrics.sample_memory(Mock(side_effect=RuntimeError('unavailable')), now=0)
        memory = metrics.summary()['device_memory']
        self.assertIsNone(memory['sampled_max_used_bytes'])
        self.assertFalse(memory['last_probe_ok'])
        metrics.sample_memory(lambda: (30, 100), now=1)
        metrics.sample_memory(lambda: (101, 100), now=2)
        memory = metrics.summary()['device_memory']
        self.assertEqual(memory['error_count'], 2)
        self.assertEqual(memory['sample_count'], 1)
        self.assertEqual(memory['last_used_bytes'], 70)

    def test_constant_space_and_snapshot(self):
        metrics = ResourceMetrics()
        for index in range(10000):
            metrics.sample_memory(lambda: (50, 100), now=index)
        snapshot = metrics.summary()
        self.assertEqual(snapshot['device_memory']['sample_count'], 10000)
        self.assertEqual(len(metrics.memory), 10)
        metrics.copy_submitted('h2d', 100)
        self.assertEqual(snapshot['cuda_counters']['h2d_submissions'], 0)
        with self.assertRaises(ValueError):
            metrics.copy_submitted('unknown', 5)


class BackendCountersTests(unittest.TestCase):
    def make_engine(self):
        engine = backend.DepthEngine.__new__(backend.DepthEngine)
        engine.metrics = ResourceMetrics()
        engine.input_bytes = int(np.prod(backend.INPUT_SHAPE) * 4)
        engine.output = np.ones(backend.OUTPUT_SHAPE, dtype=np.float32)
        engine.output_bytes = engine.output.nbytes
        engine.device_input, engine.device_output, engine.stream = 1, 2, 3
        engine.context = Mock()
        engine.context.execute_async_v3.return_value = True
        return engine

    def test_actual_infer_call_sites(self):
        engine = self.make_engine()
        success = backend.cudart.cudaError_t.cudaSuccess
        with patch.object(backend.cudart, 'cudaMemcpyAsync', return_value=(success,)) as copy:
            with patch.object(backend.cudart, 'cudaStreamSynchronize', return_value=(success,)) as sync:
                with patch.object(backend.cudart, 'cudaMemGetInfo', return_value=(success, 50, 100)):
                    for _ in range(2):
                        engine.infer(np.zeros(backend.INPUT_SHAPE, dtype=np.float32))
                    report = engine.telemetry()
        counters = report['cuda_counters']
        self.assertEqual(copy.call_count, 4)
        self.assertEqual(sync.call_count, 2)
        self.assertEqual(counters['h2d_submitted_bytes'], engine.input_bytes * 2)
        self.assertEqual(counters['d2h_submitted_bytes'], engine.output_bytes * 2)
        self.assertEqual(counters['stream_synchronizations'], 2)
        self.assertEqual(counters['completed_inferences'], 2)

    def test_failed_submission_not_counted(self):
        engine = self.make_engine()
        with patch.object(backend.cudart, 'cudaMemcpyAsync', side_effect=RuntimeError('copy')):
            with self.assertRaises(RuntimeError):
                engine.infer(np.zeros(backend.INPUT_SHAPE, dtype=np.float32))
        self.assertEqual(engine.metrics.counters['h2d_submissions'], 0)
        self.assertEqual(engine.metrics.counters['completed_inferences'], 0)

    def test_failed_synchronization_not_counted(self):
        engine = self.make_engine()
        success = backend.cudart.cudaError_t.cudaSuccess
        with patch.object(backend.cudart, 'cudaMemcpyAsync', return_value=(success,)):
            with patch.object(backend.cudart, 'cudaStreamSynchronize', side_effect=RuntimeError('sync')):
                with self.assertRaises(RuntimeError):
                    engine.infer(np.zeros(backend.INPUT_SHAPE, dtype=np.float32))
        self.assertEqual(engine.metrics.counters['d2h_submissions'], 1)
        self.assertEqual(engine.metrics.counters['stream_synchronizations'], 0)
        self.assertEqual(engine.metrics.counters['completed_inferences'], 0)
