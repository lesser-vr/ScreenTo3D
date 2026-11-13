import unittest
from unittest.mock import Mock, patch
from screento3d_app import trt_backend as backend


class BackendCleanupTests(unittest.TestCase):
    def engine(self):
        engine = backend.DepthEngine.__new__(backend.DepthEngine)
        engine.device_input, engine.device_output, engine.stream = 11, 22, 33
        engine.context = engine.engine = engine.runtime = object()
        engine.pending_work = True
        return engine

    def test_all_releases_attempted_and_no_double_free(self):
        engine = self.engine()
        ok = backend.cudart.cudaError_t.cudaSuccess
        with patch.object(backend.cudart, 'cudaFree', side_effect=[RuntimeError('free'), (ok,)]) as free, \
                patch.object(backend.cudart, 'cudaStreamDestroy', return_value=(ok,)) as destroy, \
                patch.object(backend.cudart, 'cudaStreamSynchronize', return_value=(ok,)) as sync:
            with self.assertRaises(ExceptionGroup):
                engine.close()
            engine.close()
        self.assertEqual(free.call_count, 2)
        destroy.assert_called_once_with(33)
        sync.assert_called_once_with(33)
        self.assertIsNone(engine.context)
        self.assertIsNone(engine.engine)
        self.assertIsNone(engine.runtime)

    def test_original_error_survives_failed_cleanup(self):
        engine = self.engine()
        original = ValueError('original')
        with patch.object(engine, 'close', side_effect=RuntimeError('cleanup')):
            engine.__exit__(ValueError, original, None)
        self.assertIn('cleanup', original.__notes__[0])

    def test_partial_constructor_allocation_is_released(self):
        ok = backend.cudart.cudaError_t.cudaSuccess

        def fail_after_allocation(engine, progress):
            engine.device_input = 11
            raise RuntimeError('second allocation failed')

        with patch.object(backend.DepthEngine, '_initialize', fail_after_allocation), \
                patch.object(backend.cudart, 'cudaFree', return_value=(ok,)) as free:
            with self.assertRaisesRegex(RuntimeError, 'second allocation'):
                backend.DepthEngine()
        free.assert_called_once_with(11)

    def test_no_extra_sync_for_completed_inference(self):
        engine = self.engine()
        engine.pending_work = False
        ok = backend.cudart.cudaError_t.cudaSuccess
        with patch.object(backend.cudart, 'cudaFree', return_value=(ok,)), \
                patch.object(backend.cudart, 'cudaStreamDestroy', return_value=(ok,)), \
                patch.object(backend.cudart, 'cudaStreamSynchronize') as sync:
            engine.close()
        sync.assert_not_called()
