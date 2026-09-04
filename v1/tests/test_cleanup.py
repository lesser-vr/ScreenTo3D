import io
import subprocess
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from depthsbs_app import trt_backend as backend
from depthsbs_app.pipeline import _cleanup_processes
from depthsbs_app import pipeline


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


class ProcessCleanupTests(unittest.TestCase):
    def test_failure_does_not_skip_other_process_or_pipes(self):
        first = Mock(stdin=io.BytesIO(), stdout=io.BytesIO(), stderr=io.BytesIO())
        second = Mock(stdin=io.BytesIO(), stdout=io.BytesIO(), stderr=io.BytesIO())
        first.poll.return_value = second.poll.return_value = None
        first.kill.side_effect = OSError('kill failed')
        errors = _cleanup_processes((first, second))
        self.assertEqual(len(errors), 1)
        second.kill.assert_called_once()
        second.wait.assert_called_once()
        for process in (first, second):
            for stream in (process.stdin, process.stdout, process.stderr):
                self.assertTrue(stream.closed)


class PipelineFailureTests(unittest.TestCase):
    def test_failure_and_finalization_cancel_preserve_existing_output(self):
        for scenario in ('inference', 'truncated_decode', 'encode_spawn', 'mux',
                         'cancel_after_mux', 'publish', 'cancel_before_start'):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                output, cancel = root / 'output.mp4', root / 'cancel'
                output.write_bytes(b'original')
                if scenario == 'cancel_before_start':
                    cancel.touch()
                raw = b'x' if scenario == 'truncated_decode' else bytes(16 * 16 * 3)
                decoder = Mock(stdin=None, stdout=io.BytesIO(raw), stderr=io.BytesIO())
                encoder = Mock(stdin=io.BytesIO(), stdout=None, stderr=io.BytesIO())
                for process in (decoder, encoder):
                    process.wait.return_value = 0
                    process.poll.return_value = None
                engine = Mock()
                engine.infer.return_value = np.ones((1, 518, 518), dtype=np.float32)
                if scenario == 'inference':
                    engine.infer.side_effect = RuntimeError('inference failed')
                context = Mock(__enter__=Mock(return_value=engine), __exit__=Mock(return_value=False))
                events = []

                def mux(arguments):
                    Path(arguments[-1]).touch()
                    if scenario == 'cancel_after_mux':
                        cancel.touch()
                    return subprocess.CompletedProcess(arguments, 1 if scenario == 'mux' else 0, '', 'mux failed')

                def popen(arguments, **kwargs):
                    if 'pipe:1' in arguments:
                        return decoder
                    if scenario == 'encode_spawn':
                        raise OSError('encoder spawn failed')
                    Path(arguments[-1]).touch()
                    return encoder

                with ExitStack() as stack:
                    stack.enter_context(patch.object(pipeline, 'probe_video', return_value=dict(
                        width=16, height=16, fps=30, total_frames=1)))
                    stack.enter_context(patch.object(pipeline, 'DepthEngine', return_value=context))
                    stack.enter_context(patch.object(pipeline.subprocess, 'Popen', side_effect=popen))
                    stack.enter_context(patch.object(pipeline, '_run', side_effect=mux))
                    if scenario == 'publish':
                        stack.enter_context(patch.object(Path, 'replace', side_effect=PermissionError('publish failed')))
                    with self.assertRaises((RuntimeError, OSError)):
                        pipeline.convert_video(root / 'input.mp4', output, 'performance', events.append, cancel)
                self.assertEqual(output.read_bytes(), b'original')
                self.assertFalse(cancel.exists())
                self.assertFalse(output.with_suffix('.mp4.partial.mp4').exists())
                self.assertFalse(output.with_suffix('.mp4.video-only.mp4').exists())
                self.assertFalse(any(event['event'] == 'complete' for event in events))
                if scenario != 'cancel_before_start':
                    context.__exit__.assert_called_once()
                    self.assertTrue(decoder.stdout.closed)
                    self.assertTrue(decoder.stderr.closed)
