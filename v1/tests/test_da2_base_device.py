import unittest
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch

from depthsbs_app.da2_base_device import Da2BaseDeviceDepth, Da2BaseDeviceEngine


class Da2BaseDeviceTokenTests(unittest.TestCase):
    def token(self):
        tensor = Mock()
        tensor.device = SimpleNamespace(type="cuda", index=0)
        tensor.dtype = "float32"
        tensor.shape = (1, 90, 160)
        tensor.is_contiguous.return_value = True
        tensor.data_ptr.return_value = 1234
        owner = SimpleNamespace(_check=Mock(), device=0, device_generation=3,
            torch=SimpleNamespace(float32="float32"), source_shape=(90, 160),
            stream=SimpleNamespace(cuda_stream=55))
        token = Da2BaseDeviceDepth(owner, 3, tensor, 55, ())
        owner.pending_device = token
        return owner, token

    def test_owner_generation_and_stream_are_required(self):
        owner, token = self.token()
        token.validate()
        owner.pending_device = None
        with self.assertRaisesRegex(RuntimeError, "pending owned"):
            token.validate()
        owner.pending_device = token
        owner.device_generation = 4
        with self.assertRaisesRegex(RuntimeError, "expired"):
            token.validate()
        owner.device_generation = 3
        owner.stream.cuda_stream = 99
        with self.assertRaisesRegex(RuntimeError, "binding"):
            token.validate()

    def test_rejects_wrong_shape_device_dtype_and_layout(self):
        for mutation in (lambda t: setattr(t, "shape", (1, 160, 90)),
                         lambda t: setattr(t.device, "index", 1),
                         lambda t: setattr(t, "dtype", "float16"),
                         lambda t: setattr(t.is_contiguous, "return_value", False)):
            with self.subTest(mutation=mutation):
                _, token = self.token()
                mutation(token.tensor)
                with self.assertRaisesRegex(ValueError, "tensor"):
                    token.validate()

    def test_foreign_completion_cannot_release_another_engine(self):
        engine = Da2BaseDeviceEngine.__new__(Da2BaseDeviceEngine)
        _, token = self.token()
        with self.assertRaisesRegex(ValueError, "another engine"):
            engine.complete_device(token)

    def test_graph_cleanup_failure_still_releases_engine_and_input(self):
        for failure in ('synchronize', 'reset'):
            with self.subTest(failure=failure):
                engine = Da2BaseDeviceEngine.__new__(Da2BaseDeviceEngine)
                engine.owner = threading.get_ident()
                engine.closed = False
                engine.graph = Mock()
                engine.stream = Mock()
                engine.graph_input = object()
                engine.pending_device = object()
                engine.device_generation = 0
                resource = engine.stream if failure == 'synchronize' else engine.graph
                getattr(resource, failure).side_effect = RuntimeError('injected graph cleanup')
                def parent_close():
                    engine.closed = True
                with patch('depthsbs_app.da2_base.Da2BaseEngine.close', side_effect=parent_close) as parent:
                    with self.assertRaisesRegex(RuntimeError, 'injected graph cleanup'):
                        engine.close()
                    parent.assert_called_once()
                self.assertIsNone(engine.graph_input)
                self.assertIsNone(engine.pending_device)

    def test_graph_wrong_thread_cannot_release_resources(self):
        engine = Da2BaseDeviceEngine.__new__(Da2BaseDeviceEngine)
        engine.owner = threading.get_ident() + 1
        engine.graph = Mock()
        with self.assertRaisesRegex(RuntimeError, 'owner thread'):
            engine.close()
        engine.graph.reset.assert_not_called()

    def test_graph_setting_rejects_ambiguous_value_before_loading(self):
        with patch.dict('os.environ', {'DEPTHSBS_BASE_GRAPH': 'yes'}):
            with self.assertRaisesRegex(ValueError, 'must be 0 or 1'):
                Da2BaseDeviceEngine()


if __name__ == '__main__':
    unittest.main()
