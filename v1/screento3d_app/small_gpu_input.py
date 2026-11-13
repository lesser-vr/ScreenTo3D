"""Small FP16 with owned WGC/CUDA input; same TensorRT model and raw stream."""
import cv2
import numpy as np

from .desktop_jobs import ROOT
from .trt_backend import DepthEngine, _cuda, cudart
from .gpu_runtime import GpuInputSupport

DLL_PATH = ROOT / 'out/static-sbs/small_input.dll'
DLL_SHA256 = 'd8cbabe89c36a7c3b224f8eb07cb3f458c92fb4e04280c55530f4b8d2db12849'


def cubic_coefficients(width, height):
    """Bounded shape-only setup, using IPP itself as the coefficient oracle.

    Four periodic impulse channels expose the cubic taps. The validated IPP
    path folds right horizontal border taps into the clamped source sample;
    left and vertical taps remain separate over replicated samples. Three
    periods expose those unmerged coefficients without touching captured data.
    """
    if not 16 <= width <= 4096 or not 16 <= height <= 2160:
        raise ValueError('Invalid Small input dimensions')
    if (cv2.__version__ != '4.13.0' or not cv2.ipp.useIPP() or
            '2022.2.0' not in cv2.ipp.getIppVersion()):
        raise RuntimeError('Small GPU preprocessing requires the validated OpenCV 4.13.0 IPP runtime')
    result = []
    for n, vertical in ((width, False), (height, True)):
        extent = n*3 if vertical else n
        impulse = np.eye(4, dtype=np.float32)[np.arange(extent) % 4]
        image = np.broadcast_to(impulse[None], (8, extent, 4)).copy()
        if vertical:
            image = image.transpose(1, 0, 2).copy()
        resized = cv2.resize(image, (8, 1554) if vertical else (518, 8),
                             interpolation=cv2.INTER_CUBIC)
        middle = resized[518:1036, 3] if vertical else resized[3]
        origin = np.floor((np.arange(518)+.5)*(n/518)-.5).astype(int)
        indices = origin[:,None]-1+np.arange(4)[None,:]
        indices = indices+n if vertical else np.clip(indices, 0, n-1)
        weights = np.take_along_axis(middle, indices % 4, axis=1)
        if not vertical:
            for tap in range(1,4):
                duplicate = np.any(indices[:,:tap] == indices[:,tap:tap+1], axis=1)
                weights[duplicate,tap] = 0
            left = origin < 1
            if np.any(left):
                extended = np.broadcast_to(np.eye(4,dtype=np.float32)[np.arange(n*3)%4][None],
                                            (8,n*3,4)).copy()
                unmerged = cv2.resize(extended,(1554,8),interpolation=cv2.INTER_CUBIC)[3,518:1036]
                taps = (origin[:,None]+n-1+np.arange(4)[None,:])%4
                weights[left] = np.take_along_axis(unmerged,taps,axis=1)[left]
        result.append(weights)
    return np.ascontiguousarray(np.concatenate(result), dtype=np.float32)


class SmallGpuInput(GpuInputSupport):
    def __init__(self, engine):
        super().__init__(engine, DLL_PATH, DLL_SHA256, stream=engine.torch_stream)


class SmallGpuCaptureEngine(DepthEngine):
    def __init__(self, progress=None):
        import torch
        self.torch = torch
        self.device = torch.cuda.current_device()
        self.torch_stream = self.gpu_input = None
        super().__init__(progress)
        try:
            # Non-owning wrapper: DepthEngine alone destroys the CUDA stream.
            self.torch_stream = torch.cuda.ExternalStream(int(self.stream), device=self.device)
            self.gpu_input = SmallGpuInput(self)
        except BaseException as primary:
            try:
                self.close()
            except Exception as cleanup:
                primary.add_note(f'Small engine cleanup failed: {cleanup!r}')
            raise

    def _check(self):
        self._device_check()
        if self.torch.cuda.current_device() != self.device:
            raise RuntimeError('Small GPU input used on another device')

    def close(self):
        if self.stream is not None:
            # Captures/observations may exist before the first depth submission.
            self._check()
            _cuda(cudart.cudaStreamSynchronize(self.stream))
        super().close()
        self.gpu_input = self.torch_stream = None
