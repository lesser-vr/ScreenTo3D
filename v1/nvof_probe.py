"""Owned ctypes wrapper for the isolated local NVOF diagnostic DLL."""

import ctypes as ct
import hashlib
import json
from pathlib import Path
import threading

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DLL = ROOT / "out/nvof-probe/nvof_probe.dll"
MANIFEST = DLL.parent / "build-manifest.json"
NVIDIA_HEADERS = ROOT / "out/nvof-sdk-headers"
COMMON_HEADER = NVIDIA_HEADERS / "nvOpticalFlowCommon.h"
CUDA_HEADER = NVIDIA_HEADERS / "nvOpticalFlowCuda.h"


class ProbeTiming(ct.Structure):
    _fields_ = [
        ("pack_us", ct.c_uint64),
        ("upload_us", ct.c_uint64),
        ("nvof_us", ct.c_uint64),
        ("flow_width", ct.c_uint32),
        ("flow_height", ct.c_uint32),
        ("grid", ct.c_uint32),
        ("has_flow", ct.c_uint32),
    ]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked_manifest():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    expected = {
        "dll_sha256": sha256(DLL),
        "nvidia_common_header_sha256": sha256(COMMON_HEADER),
        "nvidia_cuda_header_sha256": sha256(CUDA_HEADER),
    }
    for key, digest in expected.items():
        if manifest.get(key, "").lower() != digest.lower():
            raise ValueError(f"NVOF probe provenance mismatch: {key}")
    return manifest


def expand_flow(raw, width, height):
    if (
        not isinstance(raw, np.ndarray)
        or raw.dtype != np.int16
        or raw.ndim != 3
        or raw.shape[2] != 2
        or width < 1
        or height < 1
    ):
        raise ValueError("Invalid coarse NVOF field")
    fy, fx = raw.shape[:2]
    y = np.minimum(np.arange(height, dtype=np.int64) * fy // height, fy - 1)
    x = np.minimum(np.arange(width, dtype=np.int64) * fx // width, fx - 1)
    return np.ascontiguousarray(raw[y[:, None], x[None, :]].astype(np.float32) / 32)


class NvofProbe:
    def __init__(self, width, height):
        if not 16 <= width <= 4096 or not 16 <= height <= 2160:
            raise ValueError("Invalid NVOF dimensions")
        self.manifest = checked_manifest()
        self.width, self.height = width, height
        self.thread = threading.get_ident()
        self.dll = ct.CDLL(str(DLL))
        self.dll.nvof_probe_error.restype = ct.c_char_p
        self.dll.nvof_probe_available.restype = ct.c_int
        self.dll.nvof_probe_create.argtypes = [ct.c_int, ct.c_int]
        self.dll.nvof_probe_create.restype = ct.c_void_p
        self.dll.nvof_probe_prepare.argtypes = [
            ct.c_void_p,
            ct.c_void_p,
            ct.c_int,
            ct.c_void_p,
            ct.c_size_t,
            ct.POINTER(ProbeTiming),
        ]
        self.dll.nvof_probe_destroy.argtypes = [ct.c_void_p]
        if not self.dll.nvof_probe_available():
            raise RuntimeError("NVIDIA Optical Flow driver API is unavailable")
        self.handle = self.dll.nvof_probe_create(width, height)
        self._check(self.handle)
        self.flow = np.empty(((height + 1) // 2, (width + 1) // 2, 2), np.int16)
        self.frames = 0

    def _check(self, value):
        if not value:
            raise RuntimeError(self.dll.nvof_probe_error().decode("utf-8"))

    def _owner(self):
        if threading.get_ident() != self.thread:
            raise RuntimeError("NVOF probe used from another thread")
        if not self.handle:
            raise RuntimeError("NVOF probe is closed")

    def prepare(self, frame, *, reset=False):
        self._owner()
        if (
            not isinstance(frame, np.ndarray)
            or frame.dtype != np.uint8
            or frame.shape != (self.height, self.width, 3)
            or not frame.flags.c_contiguous
        ):
            raise ValueError("NVOF requires contiguous RGB")
        timing = ProbeTiming()
        self._check(
            self.dll.nvof_probe_prepare(
                self.handle,
                frame.ctypes.data,
                int(reset),
                self.flow.ctypes.data,
                self.flow.size,
                ct.byref(timing),
            )
        )
        expected = ((self.height + 1) // 2, (self.width + 1) // 2)
        if timing.grid != 2 or (
            timing.has_flow and (timing.flow_height, timing.flow_width) != expected
        ):
            raise RuntimeError("Unexpected NVOF result descriptor")
        self.frames += 1
        return self.flow.copy(), {
            "pack_us": int(timing.pack_us),
            "upload_us": int(timing.upload_us),
            "nvof_us": int(timing.nvof_us),
            "flow_width": int(timing.flow_width),
            "flow_height": int(timing.flow_height),
            "grid": int(timing.grid),
            "has_flow": bool(timing.has_flow),
        }

    def close(self):
        if threading.get_ident() != self.thread:
            raise RuntimeError("NVOF probe closed from another thread")
        handle, self.handle = self.handle, None
        if handle:
            self._check(self.dll.nvof_probe_destroy(handle))

    def __enter__(self):
        self._owner()
        return self

    def __exit__(self, kind, primary, tb):
        try:
            self.close()
        except Exception as error:
            if primary is None:
                raise
            primary.add_note(str(error))
