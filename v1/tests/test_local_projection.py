import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from depthsbs_app import local_projection
from depthsbs_app.main import build_parser, run_worker


class LocalProjectionTests(unittest.TestCase):
    def test_checksum_before_native_load(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            dll=root/'out/gpu-preview/DepthSBS-GPU-Preview/_internal/projection/projection.dll'
            dll.parent.mkdir(parents=True)
            dll.write_bytes(b'trusted test bytes')
            with patch.object(local_projection,'__file__',str(root/'v1/depthsbs_app/local_projection.py')), \
                    patch.object(local_projection,'DLL_SHA256',hashlib.sha256(dll.read_bytes()).hexdigest()), \
                    patch('cuda_projection_experiment.CudaProjection') as constructor:
                local_projection.factory(12,8)
                constructor.assert_called_once_with(12,8,dll_path=dll.resolve())
                constructor.reset_mock();dll.write_bytes(b'corrupt')
                with self.assertRaisesRegex(ValueError,'checksum'):local_projection.factory(12,8)
                constructor.assert_not_called()

    def test_explicit_renderer_worker_contract(self):
        for renderer in ('cpu','cuda'):
            args=build_parser().parse_args(['--mode','performance','--stereo-renderer',renderer])
            with patch('depthsbs_app.pipeline.convert_video') as convert,patch('depthsbs_app.main.emitter'):
                self.assertEqual(run_worker(args),0)
                self.assertEqual('projection_factory' in convert.call_args.kwargs,renderer=='cuda')
        with patch('depthsbs_app.pipeline.convert_video') as convert,patch('depthsbs_app.main.emitter'),patch('depthsbs_app.main.traceback.print_exc'):
            self.assertEqual(run_worker(args,gpu_preview=True),1)
            convert.assert_not_called()


if __name__=='__main__':unittest.main()
