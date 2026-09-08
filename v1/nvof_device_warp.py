"""Owned wrapper for the isolated CUDA NVOF device-depth warp."""

import ctypes as ct
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import threading

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DLL = ROOT / "out/nvof-device-warp/nvof_probe.dll"
MANIFEST = DLL.parent / "build-manifest.json"
SOURCE = ROOT / "experiments/optical_flow/nvof_cuda_probe.cu"
HEADER_ROOT = ROOT / "out/nvof-sdk-headers"
COMMON_HEADER = HEADER_ROOT / "nvOpticalFlowCommon.h"
CUDA_HEADER = HEADER_ROOT / "nvOpticalFlowCuda.h"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked_manifest():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    expected = {
        "source_sha256": sha256(SOURCE),
        "nvidia_common_header_sha256": sha256(COMMON_HEADER),
        "nvidia_cuda_header_sha256": sha256(CUDA_HEADER),
        "dll_sha256": sha256(DLL),
    }
    if manifest.get("output_name") != "nvof-device-warp":
        raise ValueError("NVOF device-warp manifest has the wrong output identity")
    for key, digest in expected.items():
        if manifest.get(key, "").lower() != digest.lower():
            raise ValueError(f"NVOF device-warp provenance mismatch: {key}")
    return manifest


class WarpTiming(ct.Structure):
    _fields_ = [
        ("pack_us", ct.c_uint64),
        ("upload_us", ct.c_uint64),
        ("nvof_us", ct.c_uint64),
        ("warp_us", ct.c_uint64),
        ("readback_us", ct.c_uint64),
        ("valid_pixels", ct.c_uint32),
    ]


def timing_dict(value):
    return {key: int(getattr(value, key)) for key, _ in WarpTiming._fields_}


def bilinear_depth_warp(previous, flow):
    """Independent float32 oracle for the native nearest-cell bilinear warp."""
    if (
        not isinstance(previous, np.ndarray)
        or previous.dtype != np.float32
        or previous.ndim != 2
        or not previous.flags.c_contiguous
        or not isinstance(flow, np.ndarray)
        or flow.dtype != np.float32
        or flow.shape != (*previous.shape, 2)
        or not flow.flags.c_contiguous
        or not np.isfinite(previous).all()
        or not np.isfinite(flow).all()
    ):
        raise ValueError("Invalid depth-warp oracle input")
    height, width = previous.shape
    y, x = np.mgrid[:height, :width].astype(np.float32)
    source_x = x + flow[:, :, 0]
    source_y = y + flow[:, :, 1]
    valid = (
        (source_x >= np.float32(1))
        & (source_x < np.float32(width - 2))
        & (source_y >= np.float32(1))
        & (source_y < np.float32(height - 2))
    )
    x0 = np.floor(source_x).astype(np.int32)
    y0 = np.floor(source_y).astype(np.int32)
    safe_x = np.clip(x0, 0, width - 2)
    safe_y = np.clip(y0, 0, height - 2)
    tx = (source_x - x0.astype(np.float32)).astype(np.float32)
    ty = (source_y - y0.astype(np.float32)).astype(np.float32)
    one = np.float32(1)
    top = (
        previous[safe_y, safe_x] * (one - tx) + previous[safe_y, safe_x + 1] * tx
    ).astype(np.float32)
    bottom = (
        previous[safe_y + 1, safe_x] * (one - tx)
        + previous[safe_y + 1, safe_x + 1] * tx
    ).astype(np.float32)
    output = (top * (one - ty) + bottom * ty).astype(np.float32)
    output[~valid] = 0
    valid &= np.isfinite(output)
    output[~valid] = 0
    return np.ascontiguousarray(output), np.ascontiguousarray(valid.astype(np.uint8))


@dataclass(frozen=True)
class DeviceWarpToken:
    owner: object
    generation: int
    pointer: int
    stream: int

    @property
    def shape(self):
        return (1, self.owner.height, self.owner.width)

    def validate(self):
        self.owner._owner()
        if self.owner.pending is not self:
            raise RuntimeError("NVOF device-warp token is not pending")
        if self.generation != self.owner.generation:
            raise RuntimeError("NVOF device-warp token expired")
        if not self.pointer or self.stream != self.owner.stream:
            raise RuntimeError("Invalid NVOF device-warp binding")


@dataclass(frozen=True)
class DeviceSeedToken:
    owner: object
    generation: int
    pointer: int
    stream: int

    @property
    def shape(self):
        return (1, self.owner.height, self.owner.width)

    def validate(self):
        self.owner._owner()
        if (
            not self.owner.seeded
            or self.owner.pending is not None
            or self.generation != self.owner.generation
        ):
            raise RuntimeError("NVOF device-seed token expired")
        if not self.pointer or self.stream != self.owner.stream:
            raise RuntimeError("Invalid NVOF device-seed binding")


class NvofDeviceWarp:
    def __init__(self, width, height):
        if not 16 <= width <= 4096 or not 16 <= height <= 2160:
            raise ValueError("Invalid NVOF device-warp dimensions")
        self.manifest = checked_manifest()
        self.width, self.height = width, height
        self.thread = threading.get_ident()
        self.dll = ct.CDLL(str(DLL))
        self.dll.nvof_probe_error.restype = ct.c_char_p
        self.dll.nvof_probe_create.argtypes = [ct.c_int, ct.c_int]
        self.dll.nvof_probe_create.restype = ct.c_void_p
        self.dll.nvof_probe_stream.argtypes = [ct.c_void_p]
        self.dll.nvof_probe_stream.restype = ct.c_uint64
        self.dll.nvof_probe_seed_device.argtypes = [
            ct.c_void_p,
            ct.c_void_p,
            ct.c_void_p,
            ct.c_uint64,
            ct.c_uint64,
            ct.c_void_p,
            ct.POINTER(ct.c_uint64),
            ct.POINTER(WarpTiming),
        ]
        self.dll.nvof_probe_warp_device.argtypes = [
            ct.c_void_p,
            ct.c_void_p,
            ct.c_uint64,
            ct.c_void_p,
            ct.c_size_t,
            ct.c_void_p,
            ct.c_size_t,
            ct.c_void_p,
            ct.c_size_t,
            ct.POINTER(ct.c_uint64),
            ct.POINTER(WarpTiming),
        ]
        self.dll.nvof_probe_complete_warp.argtypes = [
            ct.c_void_p,
            ct.c_uint64,
            ct.c_int,
        ]
        self.dll.nvof_probe_destroy.argtypes = [ct.c_void_p]
        self.handle = self.dll.nvof_probe_create(width, height)
        self._check(self.handle)
        self.stream = int(self.dll.nvof_probe_stream(self.handle))
        self._check(self.stream)
        self.generation = 0
        self.pending = None
        self.seeded = False
        self.flow_shape = ((height + 1) // 2, (width + 1) // 2, 2)

    def _check(self, value):
        if not value:
            message = self.dll.nvof_probe_error()
            raise RuntimeError(message.decode("utf-8") if message else "NVOF failure")

    def _owner(self):
        if threading.get_ident() != self.thread:
            raise RuntimeError("NVOF device warp used from another thread")
        if not self.handle:
            raise RuntimeError("NVOF device warp is closed")

    def _frame(self, frame):
        if (
            not isinstance(frame, np.ndarray)
            or frame.dtype != np.uint8
            or frame.shape != (self.height, self.width, 3)
            or not frame.flags.c_contiguous
        ):
            raise ValueError("NVOF device warp requires contiguous RGB")

    def _seed(self, frame, depth_token, *, diagnostic):
        self._owner()
        self._frame(frame)
        if self.pending is not None:
            raise RuntimeError("Complete NVOF device warp before reseeding")
        depth_token.validate()
        if tuple(depth_token.shape) != (1, self.height, self.width):
            raise ValueError("Device-depth seed shape mismatch")
        generation = self.generation + 1
        output = ct.c_uint64()
        timing = WarpTiming()
        depth = np.empty((self.height, self.width), np.float32) if diagnostic else None
        self._check(
            self.dll.nvof_probe_seed_device(
                self.handle,
                frame.ctypes.data,
                depth_token.pointer,
                depth_token.stream,
                generation,
                depth.ctypes.data if depth is not None else None,
                ct.byref(output),
                ct.byref(timing),
            )
        )
        if not output.value:
            raise RuntimeError("NVOF seed returned a null device pointer")
        self.generation = generation
        self.seeded = True
        token = DeviceSeedToken(
            self, generation, int(output.value), self.stream
        )
        token.validate()
        return token, depth, timing_dict(timing)

    def seed(self, frame, depth_token, *, diagnostic=False):
        _, depth, timing = self._seed(
            frame, depth_token, diagnostic=diagnostic
        )
        return depth, timing

    def seed_pointer(self, frame, depth_token, *, diagnostic=False):
        """Copy fresh device depth onto the owned stream and expose it briefly.

        The token is valid only until the next seed or warp. Its consumer must
        finish synchronously before advancing this object.
        """
        return self._seed(frame, depth_token, diagnostic=diagnostic)

    def warp(self, frame, *, diagnostic=False):
        self._owner()
        self._frame(frame)
        if not self.seeded:
            raise RuntimeError("Seed NVOF device depth before warping")
        if self.pending is not None:
            raise RuntimeError("Complete NVOF device warp before reuse")
        generation = self.generation + 1
        raw = np.empty(self.flow_shape, np.int16) if diagnostic else None
        depth = np.empty((self.height, self.width), np.float32) if diagnostic else None
        valid = np.empty((self.height, self.width), np.uint8) if diagnostic else None
        output = ct.c_uint64()
        timing = WarpTiming()
        self._check(
            self.dll.nvof_probe_warp_device(
                self.handle,
                frame.ctypes.data,
                generation,
                raw.ctypes.data if raw is not None else None,
                raw.size if raw is not None else 0,
                depth.ctypes.data if depth is not None else None,
                depth.size if depth is not None else 0,
                valid.ctypes.data if valid is not None else None,
                valid.size if valid is not None else 0,
                ct.byref(output),
                ct.byref(timing),
            )
        )
        token = DeviceWarpToken(self, generation, int(output.value), self.stream)
        self.generation = generation
        self.pending = token
        token.validate()
        return token, raw, depth, valid, timing_dict(timing)

    def complete(self, token, *, retain=True):
        token.validate()
        self._check(
            self.dll.nvof_probe_complete_warp(
                self.handle, token.generation, int(retain)
            )
        )
        self.pending = None
        if not retain:
            self.seeded = False

    def close(self):
        if threading.get_ident() != self.thread:
            raise RuntimeError("NVOF device warp closed from another thread")
        handle, self.handle = self.handle, None
        if handle:
            if self.pending is not None:
                self.handle = handle
                try:
                    self.complete(self.pending, retain=False)
                finally:
                    handle, self.handle = self.handle, None
            self._check(self.dll.nvof_probe_destroy(handle))
        self.pending = None
        self.seeded = False

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
