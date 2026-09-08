import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from depthsbs_app.gpu_preview import preview_factory


class PreviewBoundaryTests(unittest.TestCase):
    def test_uses_only_resolved_bundle_dll(self):
        with tempfile.TemporaryDirectory() as directory:
            dll = Path(directory) / 'projection.dll'
            dll.touch()
            with patch('depthsbs_app.gpu_preview.resource_path', return_value=dll), \
                 patch('depthsbs_app.gpu_preview.CudaProjection') as adapter:
                owner = preview_factory(12, 8)
                adapter.assert_called_once_with(12, 8, dll_path=dll.resolve())
                self.assertEqual(owner.algorithm, 'forward_zbuffer_cuda_preview')

    def test_missing_bundle_does_not_try_development_dll(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('depthsbs_app.gpu_preview.resource_path', return_value=Path(directory) / 'missing'), \
                 patch('depthsbs_app.gpu_preview.CudaProjection') as adapter:
                with self.assertRaises(FileNotFoundError):
                    preview_factory(2, 2)
                adapter.assert_not_called()

    def test_incompatibility_is_explicit_without_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            dll = Path(directory) / 'projection.dll'
            dll.touch()
            with patch('depthsbs_app.gpu_preview.resource_path', return_value=dll), \
                 patch('depthsbs_app.gpu_preview.CudaProjection', side_effect=RuntimeError('101')):
                with self.assertRaisesRegex(RuntimeError, 'No automatic fallback'):
                    preview_factory(2, 2)
