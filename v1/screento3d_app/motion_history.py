"""Owned one-frame GPU depth history; no model inference or captured host pixels."""

import ctypes as ct
import hashlib
import threading

from .desktop_jobs import ROOT
from .portable_cuda import binary
from .stereo_stability import DepthRangeClock

DLL = ROOT / "out/live-motion-static/live_motion.dll"
DLL_SHA256 = "1d59f7501f939a89c84f010ec8dc8c800c7f25b6396a38e5e89d4913746b701a"
LAYOUTS = frozenset(
    (
        "0394a7b790c92db37aaa49190e213edc65914e79625f03d38d62cf3c2911da85",
        "c795770368894d92c9f38647bed741822d55e2dea9f20c3a09a8af845411056e",
        "d8cbabe89c36a7c3b224f8eb07cb3f458c92fb4e04280c55530f4b8d2db12849",
        "54a26a5d64903ba3d47a6b0393a0d40a8a4f3b1a56b94fd7b6a7c8c29928a066",
        "85261b5df16bfa22c30dcb768640b462eb16040cd36e9844247bc9705438663f",
        "3e56bde920f0b9007203c95f045dcb85a6fdf1aaa34a3c98964dd1b200b8519a",
        "cdb88564014c7253e37ca96e4475f45f132aa366c81411b60b0577f60e510998",
        "ca84bb54ce84d426d2af383d0b8971966b10e12bae8dc851c892f3474b43c408",
        "a1abad814853a74890214f8cc95e9be853f107a7479ab3aad1afb0fda441afee",
        "a641facccfb24e60fc86debfdce4db795926e7a1c81b9a5ac545f4f3df20b857",
        "a712b91082de8e31fb7c35ab81cae51c5c4d6a1d31b014b486be410646516c40",
        "bebfc39715f120e03b6f6cc08a1c68f14892acd624e9ffc53d8861d0596116fb",
    )
)


class MotionHistory:
    def __init__(self, width, height, stream, layout, *, diagnostic=False):
        path, expected = binary(DLL, DLL_SHA256)
        if (
            layout not in LAYOUTS
            or hashlib.sha256(path.read_bytes()).hexdigest() != expected
        ):
            raise ValueError("Motion history DLL or borrowed layout checksum mismatch")
        self.thread = threading.get_ident()
        self.failed = False
        self.clock = DepthRangeClock()
        self.reset_pending = True
        self.diagnostic = diagnostic
        self.width, self.height = width, height
        self.dll = ct.CDLL(str(path))
        self.dll.motion_last_error.restype = ct.c_char_p
        self.dll.motion_create.argtypes = [ct.c_int, ct.c_int, ct.c_void_p, ct.c_int]
        self.dll.motion_create.restype = ct.c_void_p
        self.dll.motion_apply.argtypes = [
            ct.c_void_p,
            ct.c_void_p,
            ct.c_int,
            ct.c_double,
        ]
        self.dll.motion_destroy.argtypes = [ct.c_void_p]
        self.dll.motion_readback.argtypes = [ct.c_void_p] * 3
        self.dll.motion_depth.argtypes = [ct.c_void_p] * 3
        self.dll.motion_static_probe.argtypes = [ct.c_void_p,ct.c_void_p,ct.c_int,ct.POINTER(ct.c_int)]
        self.handle = ct.c_void_p(
            self.dll.motion_create(width, height, stream, int(diagnostic))
        )
        self._check(self.handle.value)

    def _check(self, ok):
        if not ok:
            self.failed = True
            raise RuntimeError(
                "Motion history: "
                + self.dll.motion_last_error().decode("utf-8", "replace")
            )

    def _owner(self):
        if self.thread != threading.get_ident() or not self.handle.value or self.failed:
            raise RuntimeError(
                "Motion history has invalid owner or failed/closed state"
            )

    def apply(self, live, source_ns, *, reset=False):
        self._owner()
        dt, reset = self.clock.update(source_ns, reset=reset or self.reset_pending)
        self._check(self.dll.motion_apply(self.handle, live, int(reset), dt))
        self.reset_pending = False

    def invalidate(self):
        self._owner()
        self.reset_pending = True

    def static_probe(self, live, compare):
        self._owner()
        pending = ct.c_int()
        self._check(self.dll.motion_static_probe(self.handle, live, int(compare), ct.byref(pending)))
        return pending.value

    def snapshot(self, live):
        self._owner()
        if not self.diagnostic:
            raise ValueError("Motion readback requires an explicit diagnostic session")
        import numpy as np

        shape = (self.height, self.width)
        depth = np.empty(shape, np.float32)
        previous = np.empty_like(depth)
        accepted = np.empty(shape, np.uint8)
        self._check(
            self.dll.motion_readback(
                self.handle, previous.ctypes.data, accepted.ctypes.data
            )
        )
        self._check(self.dll.motion_depth(self.handle, live, depth.ctypes.data))
        return depth, previous, accepted

    def read_depth(self, live, output):
        """Explicit diagnostic readback; normal rendering never calls this."""
        self._owner()
        import numpy as np

        if (
            output.shape != (self.height, self.width)
            or output.dtype != np.float32
            or not output.flags.c_contiguous
            or not output.flags.writeable
        ):
            raise ValueError("Invalid motion depth output")
        self._check(self.dll.motion_depth(self.handle, live, output.ctypes.data))

    def close(self):
        if self.thread != threading.get_ident():
            raise RuntimeError("Motion history closed from another thread")
        handle, self.handle = self.handle, ct.c_void_p()
        if handle.value:
            self._check(self.dll.motion_destroy(handle))

    def __enter__(self):
        return self

    def __exit__(self, kind, primary, tb):
        try:
            self.close()
        except Exception as error:
            if primary is None:
                raise
            primary.add_note(str(error))
