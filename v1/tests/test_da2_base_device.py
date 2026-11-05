import unittest
from types import SimpleNamespace
from unittest.mock import Mock

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


if __name__ == '__main__':
    unittest.main()
