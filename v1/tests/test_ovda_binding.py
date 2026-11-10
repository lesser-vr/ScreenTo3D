import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from depthsbs_app import ovda
from depthsbs_app.config import MODES
from depthsbs_app.main import build_parser


class OvdaTests(unittest.TestCase):
    def test_geometry(self):
        for width, height, shape in ((1056, 608, (518, 924)), (1280, 720, (518, 924)), (1920, 1080, (518, 924)), (3840,2160,(518,924)), (960,720,(518,924))):
            self.assertEqual(ovda.input_shape(dict(width=width, height=height)), shape)
        for width, height in ((3440,1440),(3840,1600),(720,1280),(640,640)):
            self.assertIn(ovda.input_shape(dict(width=width,height=height)), ovda.PROFILES)
        for width, height in ((7680, 4320), (True, 608), (0, 0)):
            with self.assertRaises(ValueError):
                ovda.input_shape(dict(width=width, height=height))

    def test_license_gate_first(self):
        with self.assertRaisesRegex(ValueError, 'non-commercial'):
            ovda.binding(None, None)

    def test_profiles_selection_and_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'nvinfer_11.dll').touch()
            records = {}
            for index, shape in enumerate(((518, 896), (518, 924))):
                data = b'local-test-plan' + bytes(index + 1)
                records[shape] = (hashlib.sha256(data).hexdigest(), len(data))
                child = root / f'{shape[0]}x{shape[1]}-{ovda.PROFILE_SUFFIX}'
                child.mkdir()
                (child / 'model.plan').write_bytes(data)
            with patch.object(ovda, 'PROFILES', records):
                self.assertEqual(len(ovda.profiles(root)), 2)
                backend = ovda.binding(root, root, True)
                with self.assertRaisesRegex(ValueError, 'every frame'):
                    backend.validate_policy(MODES['performance'])
                for mode in ('balanced', 'video-quality', 'offline-quality'):
                    backend.validate_policy(MODES[mode])
                with patch.object(ovda, 'runtime_class') as loader:
                    with self.assertRaisesRegex(ValueError, 'preflight'):
                        backend.engine_factory(None)
                    backend.input_validator(dict(width=1056, height=608))
                    backend.engine_factory(None)
                    loader.assert_called_with(False)
                    self.assertEqual(loader.return_value.call_args.kwargs['profile'], (518, 896))
                    # A missing native profile now fits an installed canvas.
                    backend.input_validator(dict(width=640, height=480))
                    backend.engine_factory(None)
                    self.assertEqual(loader.return_value.call_args.kwargs['profile'], (518, 896))
                    # Bad preflight invalidates the prior successful selection.
                    with self.assertRaises(ValueError):
                        backend.input_validator(dict(width=0, height=480))
                    with self.assertRaisesRegex(ValueError, 'preflight'):
                        backend.engine_factory(None)
                    device_backend = ovda.binding(
                        root, root, True, device_depth=True
                    )
                    device_backend.input_validator(dict(width=1056, height=608))
                    device_backend.engine_factory(None)
                    loader.assert_called_with(True)
                child = root / '518x924-fp16'
                self.assertEqual(list(ovda.profiles(child)), [(518, 924)])
                data = (child / 'model.plan').read_bytes()
                (child / 'model.plan').write_bytes(b'x' * len(data))
                with self.assertRaisesRegex(ValueError, 'checksum'):
                    ovda.profiles(root)

    def test_parser_defaults(self):
        parser = build_parser()
        default = parser.parse_args([])
        self.assertEqual(default.depth_backend, 'da2-base')
        self.assertFalse(default.ovda_noncommercial)
        parsed = parser.parse_args(['--depth-backend', 'ovda-small-c16', '--ovda-noncommercial'])
        self.assertTrue(parsed.ovda_noncommercial)

    def test_adopted_artifact_and_description_require_mixed_fp16(self):
        from depthsbs_app.model_presentation import model_info
        self.assertEqual(set(ovda.PROFILES),{(518,924)})
        self.assertEqual(ovda.PROFILE_SUFFIX,'fp16')
        self.assertEqual(ovda.RUNTIME,'tensorrt-mixed-fp16')
        self.assertEqual(model_info('ovda-small-c16')[1],'Mixed FP16')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'518x924-fp32').mkdir()
            (root/'518x924-fp32/model.plan').write_bytes(b'old engine')
            with self.assertRaisesRegex(ValueError,'mixed FP16'):ovda.profiles(root)


if __name__ == '__main__':
    unittest.main()
