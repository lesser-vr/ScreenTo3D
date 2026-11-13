# oVDA input adaptation, NC-SA-UHDV1.0; see LICENSE and README.md.
"""Pinned, same-stream FP32 preprocessing; no captured image readback."""
import ctypes as ct
import hashlib
from screento3d_app.desktop_jobs import ROOT
from screento3d_app.gpu_runtime import GpuInputSupport
from screento3d_app.ovda_geometry import content_rect, SUPPORTED_CANVASES
from screento3d_app.portable_cuda import DIRECTORY, PINS

DLL_PATH = ROOT/'out/ovda-gpu-input-resolution/ovda_input.dll'
DLL_SHA256 = 'ef4fa57630fc1ab6eeeecac39bbf3927f57c4bde1afe0cb82875a50524b294a6'


def runtime_library():
    if not DLL_PATH.is_file():
        raise RuntimeError('oVDA GPU runtime missing; run scripts/build-ovda-input.ps1')
    if hashlib.sha256(DLL_PATH.read_bytes()).hexdigest()!=DLL_SHA256:
        raise ValueError('oVDA GPU input DLL checksum mismatch')
    return ct.CDLL(str(DLL_PATH))


class OvdaGpuInput(GpuInputSupport):
    def __init__(self, engine):
        super().__init__(engine, DIRECTORY/'base_input.dll', PINS['base_input.dll'], stream=engine.stream)
        self.native=runtime_library()
        self.launch=self.native.ovda_prepare
        self.launch.argtypes=[ct.c_void_p,ct.c_size_t]+[ct.c_int]*9+[ct.c_void_p]*3
        self.launch.restype=ct.c_int
        with self.execution.scope():
            self.flag=engine.torch.empty((),dtype=engine.torch.int32,device=engine.device)

    def prepare(self, rgb, shape, output=None):
        gpu=self.execution
        gpu.require_current()
        gpu.validate_image(rgb,channels=(3,4),pitched=True)
        if tuple(shape) not in SUPPORTED_CANVASES:raise ValueError('Unsupported oVDA GPU canvas')
        h,w,channels=rgb.shape
        dims=(1,3,*shape)
        if output is None:
            output=gpu.torch.empty(dims,dtype=gpu.torch.float32,device=rgb.device)
        if (output.device!=rgb.device or output.dtype!=gpu.torch.float32 or
                tuple(output.shape)!=dims or not output.is_contiguous()):
            raise ValueError('Invalid persistent oVDA input buffer')
        code=self.launch(rgb.data_ptr(),rgb.stride(0),w,h,channels,*shape,
                         *content_rect(w,h,shape),output.data_ptr(),self.flag.data_ptr(),gpu.handle)
        if code:raise RuntimeError(f'oVDA GPU preprocessing failed: CUDA {code}')
        return output
