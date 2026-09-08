"""Explicit opt-in experimental adapter; not imported by the production pipeline."""
import ctypes
from pathlib import Path
import threading
import numpy as np


class CudaProjection:
    algorithm = 'forward_zbuffer_cuda_experimental'

    def telemetry(self):
        pixels = self.width * self.height
        return dict(scope='successful projection calls; explicit host/device copies',
            completed_eye_calls=self.calls, persistent_device_bytes=pixels * 22,
            h2d_bytes=self.calls * pixels * 11, d2h_bytes=self.calls * pixels * 3,
            stream_synchronizations=self.calls, zero_copy=False)

    def __init__(self, width, height, dll_path=None):
        if not isinstance(width, int) or not isinstance(height, int) or not (1 <= width <= 7680 and 1 <= height <= 4320):
            raise ValueError('Invalid projection dimensions')
        self.width, self.height = width, height
        self.owner_thread = threading.get_ident()
        self.handle = ctypes.c_void_p()
        path = Path(dll_path) if dll_path else Path(__file__).resolve().parents[1] / 'out/cuda-projection-spike/projection.dll'
        self.dll = ctypes.CDLL(str(path.resolve(strict=True)))
        self.dll.projection_create.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_int, ctypes.c_int]
        self.dll.projection_create.restype = ctypes.c_int
        self.dll.projection_run.argtypes = [ctypes.c_void_p] * 5 + [ctypes.c_int]
        self.dll.projection_run.restype = ctypes.c_int
        self.dll.projection_destroy.argtypes = [ctypes.c_void_p]
        self.dll.projection_destroy.restype = ctypes.c_int
        self.calls = 0
        status = self.dll.projection_create(ctypes.byref(self.handle), width, height)
        if status:
            raise RuntimeError(f'CUDA projection create failed: {status}')

    def _thread_check(self):
        if threading.get_ident() != self.owner_thread:
            raise RuntimeError('CUDA projection must be used/closed by its owner thread')

    def project(self, frame, depth, shift, conservative_coverage=False):
        self._thread_check()
        if not self.handle.value:
            raise RuntimeError('CUDA projection is closed')
        if frame.dtype != np.uint8 or depth.dtype != np.float32 or shift.dtype != np.float32:
            raise ValueError('Expected uint8 RGB and float32 depth/shift')
        shape = (self.height, self.width)
        if frame.shape != (*shape, 3) or depth.shape != shape or shift.shape != shape:
            raise ValueError('Projection shape mismatch')
        if not np.isfinite(depth).all() or not np.isfinite(shift).all() or np.max(np.abs(shift)) > 1e6:
            raise ValueError('Invalid projection numeric input')
        frame, depth, shift = (np.ascontiguousarray(a) for a in (frame, depth, shift))
        output = np.empty_like(frame)
        status = self.dll.projection_run(self.handle, frame.ctypes.data, depth.ctypes.data,
            shift.ctypes.data, output.ctypes.data, int(conservative_coverage))
        if status:
            error = RuntimeError(f'CUDA projection run failed: {status}')
            try:
                self.close()
            except Exception as cleanup:
                error.add_note(str(cleanup))
            raise error
        self.calls += 1
        return output

    def close(self):
        self._thread_check()
        handle, self.handle = self.handle, ctypes.c_void_p()
        if handle.value:
            status = self.dll.projection_destroy(handle)
            if status:
                raise RuntimeError(f'CUDA projection cleanup failed: {status}')

    def __enter__(self):
        self._thread_check()
        if not self.handle.value:
            raise RuntimeError('CUDA projection is closed')
        return self

    def __exit__(self, kind, value, traceback):
        try:
            self.close()
        except Exception as cleanup:
            if value is None:
                raise
            value.add_note(str(cleanup))
        return False
