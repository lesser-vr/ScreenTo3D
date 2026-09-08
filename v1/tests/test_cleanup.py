import io
import subprocess
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from depthsbs_app.pipeline import _cleanup_processes
from depthsbs_app import pipeline


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
                         'cancel_after_mux', 'publish', 'cancel_before_start',
                         'decode_exit', 'encode_exit', 'empty_decode', 'empty_mux', 'process_cleanup'):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                output, cancel = root / 'output.mp4', root / 'cancel'
                output.write_bytes(b'original')
                if scenario == 'cancel_before_start':
                    cancel.touch()
                raw = b'x' if scenario == 'truncated_decode' else bytes(16 * 16 * 3)
                if scenario == 'empty_decode':
                    raw = b''
                decoder = Mock(stdin=None, stdout=io.BytesIO(raw), stderr=io.BytesIO())
                encoder = Mock(stdin=io.BytesIO(), stdout=None, stderr=io.BytesIO())
                for process in (decoder, encoder):
                    process.wait.return_value = 0
                    process.poll.return_value = None
                if scenario == 'decode_exit':
                    decoder.wait.return_value = 1
                if scenario == 'encode_exit':
                    encoder.wait.return_value = 1
                engine = Mock()
                engine.infer.return_value = np.ones((1, 518, 518), dtype=np.float32)
                if scenario == 'inference':
                    engine.infer.side_effect = RuntimeError('inference failed')
                context = Mock(__enter__=Mock(return_value=engine), __exit__=Mock(return_value=False))
                events = []

                def mux(arguments):
                    Path(arguments[-1]).write_bytes(b'' if scenario == 'empty_mux' else b'mock mux payload')
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
                    if scenario == 'process_cleanup':
                        actual_cleanup = pipeline._cleanup_processes
                        def fail_cleanup(processes):
                            errors = actual_cleanup(processes)
                            if any(process is not None for process in processes):
                                errors.append(OSError('injected pipe cleanup failure'))
                            return errors
                        stack.enter_context(patch.object(pipeline, '_cleanup_processes', side_effect=fail_cleanup))
                    if scenario == 'publish':
                        stack.enter_context(patch.object(Path, 'replace', side_effect=PermissionError('publish failed')))
                    with self.assertRaises((RuntimeError, OSError, ExceptionGroup)):
                        pipeline.convert_video(root / 'input.mp4', output, 'performance', events.append, cancel)
                self.assertEqual(output.read_bytes(), b'original')
                self.assertFalse(cancel.exists())
                self.assertFalse(output.with_suffix('.mp4.partial.mp4').exists())
                self.assertFalse(output.with_suffix('.mp4.video-only.mp4').exists())
                self.assertEqual(list(root.iterdir()), [output])
                self.assertFalse(any(event['event'] == 'complete' for event in events))
                if scenario != 'cancel_before_start':
                    context.__exit__.assert_called_once()
                    self.assertTrue(decoder.stdout.closed)
                    self.assertTrue(decoder.stderr.closed)
