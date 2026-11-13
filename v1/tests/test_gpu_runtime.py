import threading
import unittest
from contextlib import nullcontext
from types import SimpleNamespace

from screento3d_app.gpu_runtime import GpuExecution


class GpuRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.thread = threading.get_ident()
        self.closed = False
        self.stream = SimpleNamespace(cuda_stream=123)
        self.current = self.stream
        def check():
            if self.closed or threading.get_ident() != self.thread:
                raise RuntimeError('Owner unavailable')
        torch = SimpleNamespace(uint8='uint8', cuda=SimpleNamespace(
            current_stream=lambda device: self.current, stream=lambda stream: nullcontext(stream)))
        self.owner = SimpleNamespace(_check=check, torch=torch, device=0)
        self.gpu = GpuExecution(self.owner,self.stream)

    def test_borrowed_handle_scope_and_expired_owner(self):
        self.assertEqual(self.gpu.handle,123)
        with self.gpu.scope() as stream:
            self.assertIs(stream,self.stream)
        self.closed = True
        for operation in (lambda:self.gpu.handle,self.gpu.scope,self.gpu.require_current):
            with self.assertRaises(RuntimeError): operation()

    def test_wrong_stream_and_thread_rejected(self):
        self.current = object()
        with self.assertRaises(RuntimeError): self.gpu.require_current()
        failures = []
        def foreign():
            try: self.gpu.scope()
            except RuntimeError: failures.append(True)
        thread = threading.Thread(target=foreign)
        thread.start()
        thread.join()
        self.assertEqual(failures,[True])

    def test_image_device_shape_and_pitch_contract(self):
        def image(*,device='cuda',index=0,dtype='uint8',shape=(16,16,3),strides=(48,3,1),contiguous=True):
            return SimpleNamespace(device=SimpleNamespace(type=device,index=index),dtype=dtype,
                ndim=len(shape),shape=shape,stride=lambda i:strides[i],is_contiguous=lambda:contiguous)
        self.gpu.validate_image(image())
        self.gpu.validate_image(image(shape=(16,16,4),strides=(80,4,1),contiguous=False),channels=(3,4),pitched=True)
        for bad in (image(device='cpu'),image(index=1),image(dtype='float32'),
                    image(shape=(16,15,3)),image(shape=(2161,16,3)),
                    image(strides=(48,1,16)),image(strides=(47,3,1)),image(contiguous=False)):
            with self.assertRaises(ValueError): self.gpu.validate_image(bad)


if __name__ == '__main__': unittest.main()
