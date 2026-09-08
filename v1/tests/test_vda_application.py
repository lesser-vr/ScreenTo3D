import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np

from depthsbs_app import vda_artifacts as artifacts
from depthsbs_app.config import MODES
from depthsbs_app.depth_backend import BackendBinding, BackendSpec
from depthsbs_app.main import build_parser
from depthsbs_app.pipeline import convert_video
from depthsbs_app.vda_preprocess import preprocess


class VdaApplicationTests(unittest.TestCase):
    def manifest(self, root):
        records = {}
        for name in ('warmup', 'cached'):
            payload = name.encode()
            (root/f'{name}.plan').write_bytes(payload)
            records[name] = dict(file=f'{name}.plan', sha256=hashlib.sha256(payload).hexdigest())
        return dict(schema=1, model_id=artifacts.MODEL_ID, input_shape=artifacts.SHAPE,
            source_revision=artifacts.SOURCE_REVISION, weight_sha256=artifacts.WEIGHT_SHA256,
            tensorrt='11.2.1.2', compute_capability=[12, 0], gpu='NVIDIA GeForce RTX 5090',
            precision='fp32', fixes=['stable-temporal-softmax', 'constant-position-resize'],
            validation=dict(passed=True, comparisons=585, atol=.001, rtol=.001), engines=records)

    def test_valid_manifest_and_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = self.manifest(root)
            (root/'manifest.json').write_text(json.dumps(data))
            self.assertEqual(artifacts.load_manifest(root), data)
            (root/'cached.plan').write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                artifacts.load_manifest(root)

    def test_unvalidated_artifacts_rejected(self):
        mutations = [lambda d: d.update(model_id='other'), lambda d: d.update(tensorrt='10.8'),
            lambda d: d.update(input_shape=[1, 1, 3, 518, 952]),
            lambda d: d.update(input_shape=[1, 1, 3, 518.0, 924]),
            lambda d: d['validation'].update(passed=False),
            lambda d: d['validation'].update(comparisons=584),
            lambda d: d.update(precision='fp16'), lambda d: d.update(fixes=[]),
            lambda d: d.update(validation=None), lambda d: d.update(engines=[]),
            lambda d: d['engines']['warmup'].update(sha256=None),
            lambda d: d['engines']['warmup'].update(file='../warmup.plan'),
            lambda d: d['engines']['cached'].update(sha256='X'*64)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for mutate in mutations:
                data = self.manifest(root)
                mutate(data)
                (root/'manifest.json').write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    artifacts.load_manifest(root)

    def test_profile_is_explicit_not_silent_stretch(self):
        self.assertEqual(artifacts.profile_shape(1056, 608), (518, 896))
        artifacts.validate_input(dict(width=1056, height=608))
        for width, height in ((1920, 1080), (640, 360), (608, 1056), (0, 608), (True, 608)):
            with self.subTest(width=width), self.assertRaises(ValueError):
                artifacts.validate_input(dict(width=width, height=height))

    def test_preprocessing_owns_contiguous_float32(self):
        frame = np.full((608, 1056, 3), 128, np.uint8)
        result = preprocess(frame)
        self.assertEqual(result.shape, (3, 518, 896))
        self.assertEqual(result.dtype, np.float32)
        self.assertTrue(result.flags.c_contiguous)
        self.assertFalse(np.shares_memory(frame, result))
        for invalid in (frame.astype(np.float32), frame[:, :, 0], np.zeros((360, 640, 3), np.uint8)):
            with self.assertRaises(ValueError):
                preprocess(invalid)

    def test_cli_backend_flag_remains_explicit(self):
        parser = build_parser()
        self.assertEqual(parser.parse_args([]).depth_backend, 'da2-base')
        self.assertEqual(
            parser.parse_args(['--mode', 'performance']).depth_backend, 'da2-small'
        )
        self.assertEqual(
            parser.parse_args(['--mode', 'video-quality']).depth_backend, 'vda-small'
        )
        self.assertEqual(
            parser.parse_args(['--mode', 'offline-quality']).depth_backend, 'vda-small'
        )
        args = parser.parse_args(['--depth-backend', 'vda-small', '--vda-engine-dir', 'engines'])
        self.assertEqual(args.vda_engine_dir, Path('engines'))
        # Low-level policy oracles retain their historical DA2 fixture; product
        # routing is owned separately and validated before worker launch.
        self.assertEqual(MODES['balanced'].depth_backend, 'da2-small')

    def test_geometry_rejected_before_output_mutation(self):
        factory = Mock()
        backend = BackendBinding(BackendSpec('vda-small', 'fake', stateful=True, requires_every_frame=True),
            factory, lambda frame: frame, artifacts.validate_input)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root/'input.mp4', root/'output.mp4'
            source.touch()
            output.write_bytes(b'preserve')
            with patch('depthsbs_app.pipeline.probe_video', return_value=dict(width=640, height=360)):
                with self.assertRaisesRegex(ValueError, '518x896'):
                    convert_video(source, output, 'video-quality', Mock(), depth_backend=backend)
            self.assertEqual(output.read_bytes(), b'preserve')
            self.assertEqual(len(list(root.iterdir())), 2)
            factory.assert_not_called()
