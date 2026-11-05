"""Borrowed GPU execution and image utilities; engines retain resource ownership."""
import ctypes as ct
import hashlib


class GpuExecution:
    """One explicit Torch stream view over an engine-owned CUDA stream.

    This adapter neither creates nor destroys streams. The engine's check owns
    thread/device/closed-state validation, including after this view is retained.
    """
    def __init__(self, owner, stream):
        owner._check()
        self.owner = owner
        self.stream = stream
        self.torch = owner.torch
        self.device = owner.device

    def check(self):
        self.owner._check()

    @property
    def handle(self):
        self.check()
        return int(self.stream.cuda_stream)

    def scope(self):
        self.check()
        return self.torch.cuda.stream(self.stream)

    def require_current(self):
        self.check()
        if self.torch.cuda.current_stream(self.device) != self.stream:
            raise RuntimeError('GPU preprocessing requires the engine stream context')

    def validate_image(self, image, *, channels=(3,), pitched=False):
        self.check()
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
            output = gpu.torch.empty((32,32,3), dtype=gpu.torch.uint8, device=rgb.device)
            code = self.dll.base_thumbnail(rgb.data_ptr(), rgb.shape[1], rgb.shape[0],
                                           output.data_ptr(), gpu.handle)
            if code:
                raise RuntimeError(f'GPU scene thumbnail failed: CUDA {code}')
            return output.cpu().numpy()
