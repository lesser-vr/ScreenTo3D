"""Pinned worker-only CUDA/D3D pool. Never imported by the GUI controller."""

import ctypes as ct
import hashlib
import os
import threading

from .desktop_jobs import ROOT
from .texture_mailbox import TexturePool

RUNTIME_SHA256 = "8bf16e363dd1fc6002be598335029925113b2afa2b9bdd00f12519a8002a9eae"


class LiveTexturePool:
    library_path = ROOT / 'out/live-texture-runtime/live_texture_runtime.dll'
    library_sha256 = RUNTIME_SHA256

    def __init__(self, width, height, *, diagnostic=False):
        path = self.library_path
        if hashlib.sha256(path.read_bytes()).hexdigest() != self.library_sha256:
            raise RuntimeError("Native texture runtime DLL checksum mismatch")
        self.thread = threading.get_ident()
        self.dll = ct.CDLL(str(path))
        self.dll.live_texture_error.restype = ct.c_char_p
        self.dll.live_pool_create.argtypes = [ct.c_int] * 3
        self.dll.live_pool_create.restype = ct.c_void_p
        self.dll.live_pool_destroy.argtypes = [ct.c_void_p]
        self.dll.live_pool_descriptor.argtypes = [ct.c_void_p] * 5
        self.dll.live_pool_publish.argtypes = [
            ct.c_void_p,
            ct.c_void_p,
            ct.c_float,
            ct.c_float,
            ct.c_int,
            ct.c_void_p,
            ct.c_int,
            ct.c_int,
        ]
        self.dll.live_pool_paint.argtypes = [ct.c_void_p, ct.c_int, ct.c_int, ct.c_int]
        self.dll.live_pool_readback.argtypes = [ct.c_void_p, ct.c_int, ct.c_void_p]
        self.width, self.height = width * 2, height
        self.handle = self.dll.live_pool_create(width, height, int(diagnostic))
        self.check(self.handle)

    def check(self, code):
        if not code:
            raise RuntimeError(self.dll.live_texture_error().decode("utf-8", "replace"))

    def owner(self):
        if threading.get_ident() != self.thread or not self.handle:
            raise RuntimeError("Invalid native texture pool owner or closed pool")

    def descriptor(self, session, generation):
        self.owner()
        handles = (ct.c_ulonglong * 2)()
        low, high, pid = ct.c_ulong(), ct.c_long(), ct.c_ulong()
        self.check(
            self.dll.live_pool_descriptor(
                self.handle, handles, ct.byref(low), ct.byref(high), ct.byref(pid)
            )
        )
        pool = TexturePool(
            session,
            generation,
            pid.value,
            self.width,
            self.height,
            low.value,
            high.value,
            tuple(handles),
        )
        pool.validate(session, os.getpid())
        return pool

    def close(self):
        if threading.get_ident() != self.thread:
            raise RuntimeError("Native texture pool closed from another thread")
        handle, self.handle = self.handle, None
        if handle:
            self.check(self.dll.live_pool_destroy(handle))

    def __enter__(self):
        self.owner()
        return self

    def __exit__(self, kind, primary, tb):
        try:
            self.close()
        except Exception as error:
            if primary is None:
                raise
            primary.add_note(str(error))
