"""Borrowed GPU execution and image utilities; engines retain resource ownership."""
import ctypes as ct
import hashlib
from contextlib import nullcontext
import numpy as np
from .portable_cuda import binary


class GpuExecution:
    """One explicit Torch stream view over an engine-owned CUDA stream.

    This adapter neither creates nor destroys streams. The engine's check owns
    thread/device/closed-state validation, including after this view is retained.
    """
    def __init__(self, owner, stream):
        owner._check()
        self.owner = owner
        self.stream = stream
        self.native = getattr(owner,'native',False)
        self.torch = None if self.native else owner.torch
        self.device = owner.device

    def check(self):
        self.owner._check()

    @property
    def handle(self):
        self.check()
        return int(self.stream.cuda_stream)

    def scope(self):
        self.check()
        if self.native:return nullcontext()
        return self.torch.cuda.stream(self.stream)

    def require_current(self):
        self.check()
        if self.native:return
        if self.torch.cuda.current_stream(self.device) != self.stream:
            raise RuntimeError('GPU preprocessing requires the engine stream context')

    def validate_image(self, image, *, channels=(3,), pitched=False):
        self.check()
        if self.native:
            from .cuda_memory import Buffer
            if (not isinstance(image,Buffer) or image.device.index!=self.device or image.dtype!=np.uint8
                    or image.ndim!=3 or image.shape[2] not in channels or not 16<=image.shape[1]<=4096
                    or not 16<=image.shape[0]<=2160):raise ValueError('Invalid native CUDA image')
            image.data_ptr();return
        if (image.device.type != 'cuda' or image.device.index != self.device or
                image.dtype != self.torch.uint8 or image.ndim != 3 or
                image.shape[2] not in channels or
                not 16 <= image.shape[1] <= 4096 or not 16 <= image.shape[0] <= 2160 or
                image.stride(2) != 1 or image.stride(1) != image.shape[2] or
                image.stride(0) < image.shape[1]*image.shape[2] or
                (not pitched and not image.is_contiguous())):
            raise ValueError('Expected owned CUDA uint8 image rows on the engine device')


class GpuInputSupport:
    """Pinned native loading and shared frame observations, independent of resize."""
    def __init__(self, engine, path, digest, *, stream):
        engine._check()
        path, digest = binary(path, digest)
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('GPU input DLL checksum mismatch')
        self.engine = engine
        self.execution = GpuExecution(engine, stream)
        self.dll = ct.CDLL(str(path))
        self.dll.base_thumbnail.argtypes = [ct.c_void_p, ct.c_int, ct.c_int, ct.c_void_p, ct.c_void_p]

    def thumbnail(self, rgb):
        gpu = self.execution
        gpu.validate_image(rgb)
        with gpu.scope():
            output = (self.engine.memory.empty((32,32,3),np.uint8) if gpu.native else
                      gpu.torch.empty((32,32,3), dtype=gpu.torch.uint8, device=rgb.device))
            code = self.dll.base_thumbnail(rgb.data_ptr(), rgb.shape[1], rgb.shape[0],
                                           output.data_ptr(), gpu.handle)
            if code:
                raise RuntimeError(f'GPU scene thumbnail failed: CUDA {code}')
            return output.download() if gpu.native else output.cpu().numpy()


class FixedCanvasGpuInput(GpuInputSupport):
    """Shared launch contract for the Base and VDA cubic-resize kernels."""
    def __init__(self, engine, path, digest, entry, content_rect):
        super().__init__(engine, path, digest, stream=engine.stream)
        self.content_rect = content_rect
        self.launch = getattr(self.dll, entry)
        self.launch.argtypes = [ct.c_void_p, ct.c_size_t] + [ct.c_int]*9 + [ct.c_void_p]*2
        self.launch.restype = ct.c_int

    def prepare(self, rgb, shape, output=None):
        gpu = self.execution
        gpu.require_current()
        gpu.validate_image(rgb, channels=(3, 4), pitched=True)
        h, w, channels = rgb.shape
        rect = self.content_rect(w, h, shape)
        dims = (1, 3, *shape)
        if output is None:
            output = (self.engine.memory.empty(dims) if gpu.native else
                      gpu.torch.empty(dims, dtype=gpu.torch.float32, device=rgb.device))
        if (output.device != rgb.device or output.dtype != (np.float32 if gpu.native else gpu.torch.float32) or
                tuple(output.shape) != dims or not output.is_contiguous()):
            raise ValueError('Invalid persistent model input buffer')
        code = self.launch(rgb.data_ptr(), rgb.stride(0), w, h, channels,
                           *shape, *rect, output.data_ptr(), gpu.handle)
        if code:
            raise RuntimeError(f'GPU preprocessing failed: CUDA {code}')
        return output
