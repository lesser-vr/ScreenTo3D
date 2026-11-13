import unittest
from screento3d_app.live_device import DeviceDepth


class Owner:
    device_generation = 1
    device_output = 123
    stream = 456
    closed = False

    def _device_check(self):
        if self.closed:
            raise RuntimeError("closed")


class DeviceDepthTests(unittest.TestCase):
    def test_current_binding(self):
        DeviceDepth(Owner(), 1, 123, 456).validate()

    def test_stale_binding(self):
        owner = Owner()
        depth = DeviceDepth(owner, 1, 123, 456)
        owner.device_generation = 2
        with self.assertRaises(RuntimeError):
            depth.validate()

    def test_closed_binding(self):
        owner = Owner()
        depth = DeviceDepth(owner, 1, 123, 456)
        owner.closed = True
        with self.assertRaises(RuntimeError):
            depth.validate()

    def test_invalid_binding(self):
        for pointer, stream in [(124, 456), (123, 457)]:
            with self.assertRaises(RuntimeError):
                DeviceDepth(Owner(), 1, pointer, stream).validate()
        with self.assertRaises(ValueError):
            DeviceDepth(Owner(), 1, 123, 456, (1, 1, 1)).validate()


if __name__ == "__main__":
    unittest.main()
