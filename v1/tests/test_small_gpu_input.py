import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from screento3d_app import small_gpu_input as small
from screento3d_app import gpu_runtime
from screento3d_app.live_small_gpu_input import LiveSmallGpuInputTexture


class SmallGpuInputTests(unittest.TestCase):
    def test_invalid_dimensions_and_unvalidated_runtime_rejected(self):
        for shape in ((15,16),(16,15),(4097,2160),(4096,2161)):
            with self.assertRaises(ValueError): small.cubic_coefficients(*shape)
        with patch.object(small.cv2.ipp, 'useIPP', return_value=False):
            with self.assertRaises(RuntimeError): small.cubic_coefficients(1920,1080)
        with patch.object(small.cv2, '__version__', 'unknown'):
            with self.assertRaises(RuntimeError): small.cubic_coefficients(1920,1080)

    def test_untrusted_dll_rejected_before_loading(self):
        with patch.object(small, 'DLL_PATH', Mock(read_bytes=lambda: b'untrusted')), \
             patch.object(gpu_runtime.ct, 'CDLL') as load:
            with self.assertRaises(ValueError):
                small.SmallGpuInput(SimpleNamespace(_check=lambda: None, torch_stream=None))
            load.assert_not_called()

    def test_engine_close_drains_capture_before_destroying_raw_stream(self):
        engine = small.SmallGpuCaptureEngine.__new__(small.SmallGpuCaptureEngine)
        engine.stream, engine.context = 42, object()
        engine.device_owner = threading.get_ident()
        engine.device = 0
        engine.torch = SimpleNamespace(cuda=SimpleNamespace(current_device=lambda: 0))
        engine.gpu_input = engine.torch_stream = object()
        calls = []
        with patch.object(small.cudart, 'cudaStreamSynchronize', side_effect=lambda stream: calls.append(('drain',stream))), \
             patch.object(small, '_cuda'), \
             patch.object(small.DepthEngine, 'close', side_effect=lambda: calls.append(('close',42))):
            engine.close()
        self.assertEqual(calls, [('drain',42),('close',42)])
        self.assertIsNone(engine.gpu_input)
        self.assertIsNone(engine.torch_stream)

    def test_native_constructor_cleans_up_when_coefficients_fail(self):
        # Failure happens before the native pool exists: borrowed resources must
        # still be released, without AttributeError hiding the original failure.
        engine = SimpleNamespace(gpu_input=SimpleNamespace(execution=SimpleNamespace(
            scope=lambda: (_ for _ in ()).throw(RuntimeError('coefficient setup')))))
        def initialize(obj, *args):
            obj.engine = engine
            obj.dll = SimpleNamespace(small_prepare=Mock(), live_post=Mock(argtypes=[]), live_post_gpu=Mock())
        with patch('screento3d_app.live_gpu_candidate.LiveGpuCandidate.__init__', initialize), \
             patch('screento3d_app.live_gpu_candidate.LiveGpuCandidate.close') as close:
            with self.assertRaisesRegex(RuntimeError, 'coefficient setup'):
                LiveSmallGpuInputTexture(1920,1080,None,engine)
            close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
