import io
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
import numpy as np
from depthsbs_app import pipeline
from depthsbs_app.depth_backend import BackendBinding, BackendSpec
from depthsbs_app.offline_depth import CenteredDepthWindow


class PublicationTests(unittest.TestCase):
    def exercise(self, failure, diagnostic_hashes=False, output_codec='h264', stateful=False, offline=False):
        decoder = Mock(stdout=io.BytesIO(bytes(16*16*3*2)), stderr=io.BytesIO())
        if stateful:
            decoder.stdout = io.BytesIO(bytes(16*16*3) + bytes([255]) * (16*16*3))
        encoder = Mock(stdin=io.BytesIO(), stderr=io.BytesIO())
        for process in (decoder, encoder):
            process.wait.return_value = process.poll.return_value = 0
        engine = Mock()
        engine.infer.return_value = np.ones((1, 16, 16), np.float32)
        engine.telemetry.return_value = {}
        engine_scope = Mock(__enter__=Mock(return_value=engine), __exit__=Mock(return_value=False))
        sequence = []
        if stateful:
            engine.reset.side_effect = lambda reason: sequence.append(reason)
            def infer(tensor):
                sequence.append('infer')
                return np.ones((1, 16, 16), np.float32)
            engine.infer.side_effect = infer
        binding = BackendBinding(
            BackendSpec('fake-video', 'test', stateful=True,
                        processing=CenteredDepthWindow.strategy if offline else 'streaming'),
            lambda progress: engine_scope,
            pipeline.preprocess,
            offline_processor_factory=(lambda: CenteredDepthWindow(radius=1)) if offline else None,
        ) if stateful else None
        projection = Mock(algorithm='test_projection')
        projection.__enter__ = Mock(return_value=projection)
        projection.__exit__ = Mock(return_value=False)
        projection.telemetry.return_value = {}
        projection.project.side_effect = lambda frame, *a, **kw: frame.copy()
        if failure == 'run':
            projection.project.side_effect = RuntimeError('projection run failed')
        if failure == 'close':
            projection.__exit__.side_effect = RuntimeError('projection close failed')
        events = []
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'output.mp4'
            output.write_bytes(b'old output')
            def mux(arguments):
                projection.__exit__.assert_called_once()
                Path(arguments[-1]).write_bytes(b'new output')
                return subprocess.CompletedProcess(arguments, 0, '', '')
            metadata = dict(width=16, height=16, fps=24, total_frames=2)
            with patch.object(pipeline, 'probe_video', return_value=metadata), \
                 patch.object(pipeline, 'DepthEngine', return_value=engine_scope), \
                 patch.object(pipeline.subprocess, 'Popen', side_effect=[decoder, encoder]) as spawn, \
                 patch.object(pipeline, '_run', side_effect=mux) as mux_call:
                if failure:
                    with self.assertRaisesRegex(RuntimeError, f'projection {failure} failed'):
                        pipeline.convert_video(Path(folder)/'input.mp4', output, 'performance', events.append,
                                               projection_factory=lambda w, h: projection)
                    mux_call.assert_not_called()
                    self.assertEqual(output.read_bytes(), b'old output')
                    self.assertFalse(any(e['event'] == 'complete' for e in events))
                else:
                    mode = 'offline-quality' if offline else ('balanced' if stateful else 'performance')
                    pipeline.convert_video(Path(folder)/'input.mp4', output, mode, events.append,
                                           projection_factory=lambda w, h: projection,
                                           diagnostic_hashes=diagnostic_hashes, output_codec=output_codec,
                                           depth_backend=binding)
                    if stateful:
                        self.assertEqual(sequence, ['start', 'infer', 'scene_cut', 'infer'])
                        self.assertEqual(events[-1]['depth_backend']['model_id'], 'fake-video')
                    if offline:
                        self.assertTrue(events[-1]['telemetry']['offline_depth']['enabled'])
                        self.assertEqual(events[-1]['telemetry']['offline_depth']['emitted_frames'], 2)
                        self.assertEqual(events[-1]['telemetry']['scheduling_contract']['offline_depth_window_capacity'], 3)
                    self.assertEqual(output.read_bytes(), b'new output')
                    self.assertEqual(events[-1]['event'], 'complete')
                    self.assertEqual(events[-1]['output_codec'], output_codec)
                    command = spawn.call_args_list[1].args[0]
                    self.assertEqual(command[command.index('-c:v') + 1], 'hevc_nvenc' if output_codec == 'hevc' else 'h264_nvenc')
                    self.assertEqual(command[command.index('-tag:v') + 1], 'hvc1' if output_codec == 'hevc' else 'avc1')
                    hashes = events[-1]['telemetry']['diagnostic_hashes']
                    if diagnostic_hashes:
                        self.assertEqual(hashes['decoded_rgb'], hashlib.sha256(bytes(16*16*3*2)).hexdigest())
                        self.assertEqual(hashes['sbs_rgb'], hashlib.sha256(bytes(16*16*3*4)).hexdigest())
                        expected_depth = np.ones((1, 16, 16), np.float32).tobytes() * 2
                        self.assertEqual(hashes['depth'], hashlib.sha256(expected_depth).hexdigest())
                    else:
                        self.assertIsNone(hashes)
            projection.__exit__.assert_called_once()
            engine_scope.__exit__.assert_called_once()

    def test_success_closes_before_mux_and_publication(self):
        self.exercise(None)

    def test_diagnostic_hashes_are_explicit_and_correct(self):
        self.exercise(None, diagnostic_hashes=True)

    def test_hevc_encoder_and_publication(self):
        self.exercise(None, output_codec='hevc')

    def test_stateful_start_and_cut_reset_before_inference(self):
        self.exercise(None, stateful=True)

    def test_offline_window_preserves_order_count_and_publication(self):
        self.exercise(None, stateful=True, offline=True)

    def test_projection_failure_preserves_prior_output(self):
        self.exercise('run')

    def test_projection_close_failure_preserves_prior_output(self):
        self.exercise('close')
