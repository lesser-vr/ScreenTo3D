import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np
import cv2

from screento3d_app import vda_artifacts as artifacts
from screento3d_app.depth_backend import vda_binding
from screento3d_app.pipeline import convert_video
from screento3d_app.vda_preprocess import preprocess
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
            root = Path(directory).resolve(strict=True)
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
            root = Path(directory).resolve(strict=True)
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
            with patch('screento3d_app.pipeline.probe_video', return_value=dict(width=1920, height=1080)):
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
            for width, height in ((4097, 1080), (1080, 2161), (0, 768), (True, 1080)):
                with self.assertRaises(ValueError):
                    artifacts.select_artifact(profiles, dict(width=width, height=height))

    def test_fit_selects_canvas_and_centers_odd_padding(self):
        profiles = {shape: shape for shape in artifacts.PROFILES.values()}
        for width, height, canvas, rect in (
                (3440, 1440, (518, 924), (65, 0, 387, 924)),
                (1440, 1080, (518, 896), (0, 102, 518, 691)),
                (1080, 1920, (518, 896), (0, 302, 518, 291)),
                (1920, 1080, (518, 924), (0, 0, 518, 924))):
            self.assertEqual(artifacts.select_artifact(profiles, dict(width=width, height=height)), canvas)
            self.assertEqual(artifacts.content_rect(width, height, canvas), rect)
        self.assertEqual(artifacts.select_artifact({(518, 924): 'only'}, dict(width=600, height=800)), 'only')

    def test_native_pixels_and_replicated_padding(self):
        rng = np.random.default_rng(19)
        for w, h, shape in ((320, 180, (518, 924)), (528, 304, (518, 896)), (180, 320, (518, 896))):
            frame = rng.integers(0, 256, (h, w, 3), dtype=np.uint8)
            y, x, rh, rw = artifacts.content_rect(w, h, shape)
            content = cv2.resize(frame.astype(np.float32)/255, (rw, rh), interpolation=cv2.INTER_CUBIC)
            ref = np.pad(content, ((y, shape[0]-rh-y), (x, shape[1]-rw-x), (0, 0)), mode='edge')
            ref = ((ref-[.485,.456,.406])/[.229,.224,.225]).transpose(2,0,1).astype(np.float32)
            np.testing.assert_array_equal(preprocess(frame, shape), ref)
