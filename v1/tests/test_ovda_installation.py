from contextlib import ExitStack
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from depthsbs_app.ovda_installation import installation_report


class InstallationTests(unittest.TestCase):
    def test_missing_components_are_actionable_without_engine_import(self):
        with tempfile.TemporaryDirectory() as temp, patch('depthsbs_app.ovda.runtime_class',side_effect=AssertionError('GPU import')):
            with patch('depthsbs_app.ovda_installation.subprocess.run',side_effect=FileNotFoundError('nvidia-smi missing')):
                report=installation_report(Path(temp),Path(temp),Path(temp),'cuda')
            self.assertFalse(report['ready'])
            names={r['component'] for r in report['checks'] if not r['ready']}
            self.assertTrue({'engine profiles','GPU','TensorRT DLLs','media tools'} <= names)

    def test_cpu_stereo_does_not_require_cuda_projection(self):
        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            root=Path(temp)
            for name in ('nvinfer_11.dll','ffmpeg.exe','ffprobe.exe'):(root/name).touch()
            stack.enter_context(patch('depthsbs_app.ovda.profiles',return_value={(518,924):root}))
            stack.enter_context(patch('depthsbs_app.local_projection.checked_dll',side_effect=ValueError('not installed')))
            stack.enter_context(patch('depthsbs_app.ovda_installation.importlib.metadata.version',side_effect=lambda n:{'torch':'2.7.1+cu128','tensorrt':'11.2.1.2','numpy':'2.5.2'}[n]))
            stack.enter_context(patch('depthsbs_app.ovda_installation.subprocess.run',return_value=subprocess.CompletedProcess([],0,'NVIDIA GeForce RTX 5090, 616.56\n','')))
            self.assertTrue(installation_report(root,root,root,'cpu')['ready'])
            self.assertFalse(installation_report(root,root,root,'cuda')['ready'])


if __name__=='__main__':unittest.main()
