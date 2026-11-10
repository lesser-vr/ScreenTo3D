import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from depthsbs_app import pipeline


class OutputLimitTests(unittest.TestCase):
    def test_hevc_accepts_4k_and_boundary(self):
        for width in (3840, 4096):
            with self.subTest(width=width), patch.object(pipeline, '_run', return_value=self.probe_result(width)):
                self.assertEqual(pipeline.probe_video(Path('input.mp4'), 'hevc')['width'], width)

    def test_hevc_rejects_width_above_boundary(self):
        with patch.object(pipeline, '_run', return_value=self.probe_result(4097)):
            with self.assertRaisesRegex(ValueError, '8192'):
                pipeline.probe_video(Path('input.mp4'), 'hevc')

    def test_invalid_codec_fails_before_probe(self):
        with patch.object(pipeline, '_run') as probe:
            with self.assertRaisesRegex(ValueError, 'Unknown output codec'):
                pipeline.probe_video(Path('input.mp4'), 'invalid')
            probe.assert_not_called()

    def probe_result(self, width):
        payload = {'streams': [{'codec_type': 'video', 'width': width, 'height': 1080,
                   'avg_frame_rate': '30/1', 'duration': '1', 'nb_frames': '30', 'codec_name': 'h264'}]}
        return subprocess.CompletedProcess([], 0, json.dumps(payload), '')

    def test_4096_output_width_boundary_allowed(self):
        with patch.object(pipeline, '_run', return_value=self.probe_result(2048)):
            self.assertEqual(pipeline.probe_video(Path('input.mp4'))['width'], 2048)

    def test_4k_rejected_before_backend_and_previous_output_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / 'input.mp4', Path(directory) / 'output.mp4'
            output.write_bytes(b'prior output')
            events = []
            with patch.object(pipeline, '_run', return_value=self.probe_result(3840)), \
                 patch.object(pipeline, 'DepthEngine') as engine:
                with self.assertRaisesRegex(ValueError, '7680.*4096'):
                    pipeline.convert_video(source, output, 'performance', events.append)
                engine.assert_not_called()
            self.assertEqual(output.read_bytes(), b'prior output')
            self.assertEqual(events, [])

    def test_first_width_above_limit_rejected(self):
        with patch.object(pipeline, '_run', return_value=self.probe_result(2049)):
            with self.assertRaisesRegex(ValueError, '4098.*4096'):
                pipeline.probe_video(Path('input.mp4'))

    def test_half_sbs_accepts_4k_with_h264(self):
        with patch.object(pipeline, '_run', return_value=self.probe_result(3840)):
            self.assertEqual(pipeline.probe_video(Path('input.mp4'), 'h264', 'half-sbs')['width'], 3840)

    def test_top_bottom_checks_encoded_height(self):
        payload = json.loads(self.probe_result(3840).stdout)
        payload['streams'][0]['height'] = 2160
        result = subprocess.CompletedProcess([], 0, json.dumps(payload), '')
        with patch.object(pipeline, '_run', return_value=result):
            with self.assertRaisesRegex(ValueError, '3840x4320'):
                pipeline.probe_video(Path('input.mp4'), 'h264', 'full-tb')
            self.assertEqual(pipeline.probe_video(Path('input.mp4'), 'hevc', 'full-tb')['height'], 2160)
