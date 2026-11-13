import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from screento3d_app import pipeline


class PipelineLifecycleTests(unittest.TestCase):
    def test_completed_job_reports_disjoint_lifecycle(self):
        metadata = dict(width=16, height=16, fps=30, total_frames=2)
        decoder = Mock(stdout=io.BytesIO(bytes(16 * 16 * 3 * 2)), stderr=io.BytesIO())
        encoder = Mock(stdin=io.BytesIO(), stderr=io.BytesIO())
        for process in (decoder, encoder):
            process.wait.return_value = 0
            process.poll.return_value = 0
        engine = Mock()
        engine.infer.return_value = np.ones((1, 518, 518), dtype=np.float32)
        engine.telemetry.return_value = {'fake_backend': True}
        context = Mock()
        context.__enter__ = Mock(return_value=engine)
        context.__exit__ = Mock(return_value=False)
        events = []
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'output.mp4'

            def mux(arguments,**kwargs):
                Path(arguments[-1]).write_bytes(b'mock mux payload')
                return subprocess.CompletedProcess(arguments, 0, '', '')

            with patch.object(pipeline, 'probe_video', return_value=metadata), \
                    patch.object(pipeline, 'DepthEngine', return_value=context), \
                    patch.object(pipeline.subprocess, 'Popen', side_effect=[decoder, encoder]), \
                    patch.object(pipeline, '_run', side_effect=mux), \
                    patch.object(pipeline, 'verify_output'):
                result = pipeline.convert_video(Path(folder) / 'input.mp4', output,
                                                'performance', events.append)
            self.assertTrue(output.exists())
        timing = result['telemetry']['lifecycle_seconds']
        self.assertEqual(set(timing), {
            'engine_startup', 'pipeline_setup', 'frame_loop', 'decode_drain',
            'encode_drain', 'resource_snapshot', 'backend_close', 'audio_mux', 'publish',
        })
        self.assertTrue(all(value >= 0 for value in timing.values()))
        self.assertLessEqual(sum(timing.values()), result['elapsed_seconds'])
        self.assertGreaterEqual(result['telemetry']['job_elapsed_seconds'], result['elapsed_seconds'])
        self.assertEqual(events[-1], result)
        self.assertEqual(result['frames'], 2)
        self.assertEqual(engine.infer.call_count, 1)
        context.__exit__.assert_called_once()
