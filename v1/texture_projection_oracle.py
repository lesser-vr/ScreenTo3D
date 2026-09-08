"""Test-only native texture projection oracle; never imported by the live app."""

import ctypes as ct
import hashlib
import threading

import numpy as np

from depthsbs_app.desktop_jobs import ROOT
from depthsbs_app.live_gpu_candidate import DLL_SHA256

TEXTURE_SHA256 = "636937f85c2fc483e7748c63951149f5696fda5bc0f8685031e35f0386d0d0b6"
PUBLISH_SHA256 = "85a0ce65aa39b051f922906024b88f0995001233fe5e3fb66fab20a0f3c29e7d"
POOL_SHA256 = "7a35c1a134edd3bdeb229f9d52bfabe749ebac42d5305c8998db8feda9656110"
BORROWED_LAYOUT_DLL_SHA256 = (
    "946225fb6abaff0f9e94bea212995bb073da97fb461d5ff062886a388fae4448"
)


class TextureProjectionOracle:
    def __init__(self, gpu, *, publish=False, pool=False, diagnostic=True):
        gpu._owner()
        if DLL_SHA256 != BORROWED_LAYOUT_DLL_SHA256:
            raise ValueError("Borrowed native layout has not been revalidated")
        publish = publish or pool
        self.publish = publish
        path = ROOT / (
            "out/live-texture-pool/live_texture_pool.dll"
            if pool
            else "out/live-texture-publish/live_texture_publish.dll"
            if publish
            else "out/live-texture-projection/live_texture_projection.dll"
        )
        if hashlib.sha256(path.read_bytes()).hexdigest() != (
            POOL_SHA256 if pool else PUBLISH_SHA256 if publish else TEXTURE_SHA256
        ):
            raise ValueError("Texture oracle DLL checksum mismatch")
        self.gpu = gpu
        self.thread = threading.get_ident()
        self.dll = ct.CDLL(str(path))
        if pool:
            # Same oracle operations, explicitly bound to the pool ABI. Never
            # pass an OwnedTexturePool pointer to a ProjectionTexture export.
            for operation in ("create", "destroy", "publish", "readback"):
                setattr(
                    self.dll,
                    f"live_texture_{operation}",
                    getattr(self.dll, f"live_pool_{operation}"),
                )
        self.dll.live_texture_error.restype = ct.c_char_p
        self.dll.live_texture_create.argtypes = [ct.c_int] * (3 if pool else 2)
        self.dll.live_texture_create.restype = ct.c_void_p
        self.dll.live_texture_project.argtypes = [
            ct.c_void_p,
            ct.c_void_p,
            ct.c_float,
            ct.c_float,
            ct.c_int,
            ct.c_void_p,
        ]
        self.dll.live_texture_destroy.argtypes = [ct.c_void_p]
        if publish:
            self.dll.live_texture_publish.argtypes = [
                ct.c_void_p,
                ct.c_void_p,
                ct.c_float,
                ct.c_float,
                ct.c_int,
                ct.c_void_p,
                ct.c_int,
                ct.c_int,
            ]
            self.dll.live_texture_readback.argtypes = [
                ct.c_void_p,
                ct.c_int,
                ct.c_void_p,
            ]
            self.slot = 0
        self.handle = self.dll.live_texture_create(
            gpu.width, gpu.height, *([int(diagnostic)] if pool else [])
        )
        self._check(self.handle)
        self.output = (
            np.empty((gpu.height, gpu.width * 2, 4), np.uint8) if diagnostic else None
        )

    def _check(self, value):
        if not value:
            raise RuntimeError(self.dll.live_texture_error().decode("utf-8"))

    def compare(self, expected):
        self.gpu._owner()
        if not self.handle:
            raise RuntimeError("Texture oracle closed")
        policy = self.gpu.policy
        if self.publish:
            self._check(
                self.dll.live_texture_publish(
                    self.handle,
                    self.gpu.handle,
                    policy.convergence,
                    max(1.0, self.gpu.width * policy.divergence),
                    int(policy.conservative_stereo_coverage),
                    None,
                    self.slot,
                    0,
                )
            )
            self._check(
                self.dll.live_texture_readback(
                    self.handle, self.slot, self.output.ctypes.data
                )
            )
            self.slot = 1 - self.slot
            return bool(
                np.array_equal(self.output[:, :, :3], expected)
                and np.all(self.output[:, :, 3] == 255)
            )
        self._check(
            self.dll.live_texture_project(
                self.handle,
                self.gpu.handle,
                policy.convergence,
                max(1.0, self.gpu.width * policy.divergence),
                int(policy.conservative_stereo_coverage),
                self.output.ctypes.data,
            )
        )
        return bool(
            np.array_equal(self.output[:, :, :3], expected)
            and np.all(self.output[:, :, 3] == 255)
        )

    def close(self):
        if threading.get_ident() != self.thread:
            raise RuntimeError("Texture oracle close from another thread")
        handle, self.handle = self.handle, None
        if handle:
            self._check(self.dll.live_texture_destroy(handle))

    def __enter__(self):
        return self

    def __exit__(self, kind, primary, tb):
        try:
            self.close()
        except Exception as error:
            if primary is None:
                raise
            primary.add_note(str(error))
