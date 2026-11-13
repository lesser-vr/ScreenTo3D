"""Session-owned GPU background workspace; leaves the model/live ABI unchanged."""
import ctypes as ct
import hashlib
import threading

import numpy as np

from .desktop_jobs import ROOT
from .motion_history import LAYOUTS
from .portable_cuda import PINS

DLL = ROOT / 'out/portable-cuda/flat_background.dll'
DLL_SHA256 = PINS['flat_background.dll']


def color_bounds(color, tolerance):
    """Same float32 predicate and inclusive byte limits as uniform_color_mask."""
    accepted = np.abs(np.arange(256, dtype=np.float32)[:, None] - color) <= tolerance * 255
    if not accepted.any(axis=0).all():
        return None
    lower = accepted.argmax(axis=0)
    upper = 255 - accepted[::-1].argmax(axis=0)
    return tuple(sum(int(values[c]) << (8*c) for c in range(3)) for values in (lower, upper))


class FlatBackground:
    def __init__(self, width, height, stream, layout):
        if layout not in LAYOUTS or hashlib.sha256(DLL.read_bytes()).hexdigest() != DLL_SHA256:
            raise ValueError('Background DLL or borrowed renderer layout checksum mismatch')
        self.thread = threading.get_ident()
        self.failed = False
        self.readback_bytes = self.syncs = 0
        self.dll = ct.CDLL(str(DLL))
        self.dll.flat_create.argtypes = [ct.POINTER(ct.c_void_p), ct.c_int, ct.c_int, ct.c_void_p]
        self.dll.flat_destroy.argtypes = [ct.c_void_p]
        self.dll.flat_apply.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_int, ct.c_float, ct.c_int, ct.POINTER(ct.c_int)]
        self.handle = ct.c_void_p()
        self._check(self.dll.flat_create(ct.byref(self.handle), width, height, stream))

    def _check(self, status):
        if status:
            self.failed = True
            raise RuntimeError(f'GPU background refinement failed ({status}); restart the session')

    def apply(self, live, bounds, coverage, radius):
        if self.thread != threading.get_ident() or not self.handle.value or self.failed:
            raise RuntimeError('Invalid background workspace owner or failed/closed state')
        applied = ct.c_int()
        self._check(self.dll.flat_apply(self.handle, live, *bounds, coverage, radius, ct.byref(applied)))
        self.readback_bytes = 4 if applied.value == 0 else 12
        self.syncs = 1 if applied.value == 0 else (2 if applied.value == -1 else 3)
        return applied.value == 1

    def close(self):
        if self.thread != threading.get_ident():
            raise RuntimeError('Background workspace close from another thread')
        handle, self.handle = self.handle, ct.c_void_p()
        if handle.value:
            self._check(self.dll.flat_destroy(handle))
