"""Pinned source-checkout CUDA preprocessing, preserving Base's input contract."""
import ctypes as ct

from .da2_base import content_rect
from .desktop_jobs import ROOT
from .gpu_runtime import GpuInputSupport

DLL_PATH = ROOT / 'out/base-input/base_input.dll'
DLL_SHA256 = '0af243632a9bd59e71cdca6abf0c61a44b4b73f161f86dc1d4df24897f8843cb'


class BaseGpuInput(GpuInputSupport):
    def __init__(self, engine):
        super().__init__(engine, DLL_PATH, DLL_SHA256, stream=engine.stream)
        self.dll.base_prepare.argtypes = [ct.c_void_p, ct.c_size_t] + [ct.c_int]*9 + [ct.c_void_p]*2
        self.dll.base_prepare.restype = ct.c_int

    def prepare(self, rgb, output=None):
        engine = self.engine
        gpu = self.execution
        gpu.require_current()
        gpu.validate_image(rgb, channels=(3,4), pitched=True)
        torch = gpu.torch
        h, w, channels = rgb.shape
        top, left, rh, rw = content_rect(w, h, engine.shape)
        if output is None:
            output = torch.empty((1, 3, *engine.shape), dtype=torch.float32, device=rgb.device)
        if (output.device != rgb.device or output.dtype != torch.float32 or
                tuple(output.shape) != (1,3,*engine.shape) or not output.is_contiguous()):
            raise ValueError('Invalid persistent Base input buffer')
        code = self.dll.base_prepare(rgb.data_ptr(), rgb.stride(0), w, h, channels,
            *engine.shape, top, left, rh, rw, output.data_ptr(), gpu.handle)
        if code:
            raise RuntimeError(f'Base GPU preprocessing failed: CUDA {code}')
        return output
