"""Pinned local paired-eye CUDA handoff; no native capture/Qt texture sharing."""

import ctypes
import hashlib
import numpy as np

from cuda_projection_experiment import CudaProjection
from .desktop_jobs import ROOT

DLL_SHA256 = "e01f922faab7d839febe084bd113df25c98ce72e654ed7889b465e6a6be9ec73"


class LiveProjection(CudaProjection):
    algorithm = "forward_zbuffer_cuda_paired_local"

    def __init__(self, width, height):
        path = ROOT / "out/cuda-projection-preview/projection.dll"
        if (
            not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != DLL_SHA256
        ):
            raise ValueError(
                "라이브 CUDA DLL 검증 실패: 검증된 로컬 빌드가 필요합니다."
            )
        super().__init__(width, height, dll_path=path)
        self.dll.projection_run_pair.argtypes = [ctypes.c_void_p] * 6 + [ctypes.c_int]
        self.dll.projection_run_pair.restype = ctypes.c_int
        self.pairs = 0

    def project_pair(self, frame, depth, shift, conservative_coverage=False):
        self._thread_check()
        if not self.handle.value:
            raise RuntimeError("CUDA projection is closed")
        shape = (self.height, self.width)
        if (
            frame.dtype != np.uint8
            or depth.dtype != np.float32
            or shift.dtype != np.float32
            or frame.shape != (*shape, 3)
            or depth.shape != shape
            or shift.shape != shape
        ):
            raise ValueError("Invalid paired projection buffers")
        if (
            not np.isfinite(depth).all()
            or not np.isfinite(shift).all()
            or np.max(np.abs(shift)) > 1e6
        ):
            raise ValueError("Invalid projection numeric input")
        frame, depth, shift = (np.ascontiguousarray(a) for a in (frame, depth, shift))
        left, right = np.empty_like(frame), np.empty_like(frame)
        status = self.dll.projection_run_pair(
            self.handle,
            frame.ctypes.data,
            depth.ctypes.data,
            shift.ctypes.data,
            left.ctypes.data,
            right.ctypes.data,
            int(conservative_coverage),
        )
        if status:
            error = RuntimeError(f"CUDA paired projection failed: {status}")
            try:
                self.close()
            except Exception as cleanup:
                error.add_note(str(cleanup))
            raise error
        self.pairs += 1
        return left, right

    def telemetry(self):
        pixels = self.width * self.height
        return dict(
            completed_pairs=self.pairs,
            persistent_device_bytes=pixels * 22,
            h2d_bytes=self.pairs * pixels * 11,
            d2h_bytes=self.pairs * pixels * 6,
            stream_synchronizations=self.pairs,
            zero_copy=False,
        )
