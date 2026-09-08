import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np

from depthsbs_app import vda_artifacts as artifacts
from depthsbs_app.depth_backend import vda_binding
from depthsbs_app.pipeline import convert_video
from depthsbs_app.vda_preprocess import preprocess
import test_vda_application as helpers


class VdaProfileTests(unittest.TestCase):
    def artifact(self, root, profile):
        child = root/f'{profile}-fp32'
        child.mkdir()
        data = helpers.VdaApplicationTests().manifest(child)
        data['input_shape'] = [1, 1, 3, *artifacts.PROFILES[profile]]
        (child/'manifest.json').write_text(json.dumps(data))
        return child

    def test_standard_widescreen_preprocess_and_cache_contract(self):
        for width, height in ((640, 360), (1280, 720), (1920, 1080), (3840, 2160)):
            self.assertEqual(artifacts.profile_shape(width, height), (518, 924))
            artifacts.validate_input(dict(width=width, height=height), (518, 924))
        result = preprocess(np.zeros((360, 640, 3), np.uint8), (518, 924))
        self.assertEqual(result.shape, (3, 518, 924))
        self.assertTrue(result.flags.c_contiguous)
        self.assertEqual(artifacts.cache_layout((518, 924)),
            [(2442, 192)]*2 + [(627, 384)]*2 + [(2442, 64)]*2 + [(9768, 64)]*2)
        self.assertEqual(artifacts.cache_layout((518, 896))[0], (2368, 192))

    def test_catalog_and_explicit_artifact_select_exact_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = self.artifact(root, '518x896')
            wide = self.artifact(root, '518x924')
            profiles = artifacts.artifact_profiles(root)
            self.assertEqual(artifacts.select_artifact(profiles, dict(width=1056, height=608)), original)
            self.assertEqual(artifacts.select_artifact(profiles, dict(width=1920, height=1080)), wide)
            self.assertEqual(artifacts.artifact_profiles(wide), {(518, 924): wide})
            with self.assertRaisesRegex(ValueError, 'No matching'):
                artifacts.select_artifact(artifacts.artifact_profiles(original), dict(width=1920, height=1080))

    def test_mislabeled_or_corrupt_profiles_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wide = self.artifact(root, '518x924')
            path = wide/'manifest.json'
            data = json.loads(path.read_text())
            data['input_shape'] = artifacts.SHAPE
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'disagree'):
                artifacts.artifact_profiles(root)
            data['input_shape'] = [1, 1, 3, 518, 924]
            path.write_text(json.dumps(data))
            (wide/'warmup.plan').write_bytes(b'corruption')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                artifacts.artifact_profiles(root)

    def test_missing_profile_preserves_output_and_does_not_import_gpu(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.artifact(root, '518x896')
            (root/'nvinfer_11.dll').touch()
            binding = vda_binding(root, root)
            source, output = root/'input.mp4', root/'output.mp4'
            source.touch()
            output.write_bytes(b'prior')
            with patch('depthsbs_app.pipeline.probe_video', return_value=dict(width=1920, height=1080)):
                with self.assertRaisesRegex(ValueError, 'No matching'):
                    convert_video(source, output, 'video-quality', Mock(), depth_backend=binding)
            self.assertEqual(output.read_bytes(), b'prior')
            with self.assertRaisesRegex(ValueError, 'preflight'):
                binding.engine_factory(None)

    def test_empty_and_unsupported_geometry_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, 'No validated'):
                artifacts.artifact_profiles(root)
            self.artifact(root, '518x924')
            profiles = artifacts.artifact_profiles(root)
            for width, height in ((1080, 1920), (1024, 768), (2560, 1080)):
                with self.assertRaises(ValueError):
                    artifacts.select_artifact(profiles, dict(width=width, height=height))
