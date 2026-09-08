import unittest
from types import SimpleNamespace

import torch

from depthsbs_app.vda_device import VdaDeviceDepth


class FakeTensor:
    device = SimpleNamespace(type="cuda")
    dtype = torch.float32
    shape = (1, 1080, 1920)

    @staticmethod
    def data_ptr():
        return 1234


class FakeOwner:
    def __init__(self):
        self.pending_device = None
        self.device_generation = 7
        self.shape = (1080, 1920, 3)
        self.stream = SimpleNamespace(cuda_stream=55)
        self.checked = 0

    def _check(self):
        self.checked += 1


class VdaDeviceDepthTests(unittest.TestCase):
    def token(self):
        owner = FakeOwner()
        token = VdaDeviceDepth(owner, 7, FakeTensor(), 55, ())
        owner.pending_device = token
        return owner, token

    def test_valid_owned_token(self):
        owner, token = self.token()
        token.validate()
        self.assertEqual(token.pointer, 1234)
        self.assertEqual(owner.checked, 1)

    def test_rejects_foreign_or_expired_token(self):
        owner, token = self.token()
        owner.pending_device = object()
        with self.assertRaisesRegex(RuntimeError, "pending owned"):
            token.validate()
        owner.pending_device = token
        owner.device_generation += 1
        with self.assertRaisesRegex(RuntimeError, "expired"):
            token.validate()

    def test_rejects_wrong_stream(self):
        owner, token = self.token()
        owner.stream.cuda_stream = 99
        with self.assertRaisesRegex(RuntimeError, "binding"):
            token.validate()


if __name__ == "__main__":
    unittest.main()
