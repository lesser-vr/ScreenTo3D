"""Explicit native delivery; identical inherited postprocessing and mode policy."""

from .live_gpu_candidate import LiveGpuCandidate, DLL_SHA256
from .live_texture_pool import LiveTexturePool

BORROWED_LAYOUT_SHA256 = (
    "946225fb6abaff0f9e94bea212995bb073da97fb461d5ff062886a388fae4448"
)


class LiveGpuTexture(LiveGpuCandidate):
    def __init__(self, width, height, policy, engine, *, diagnostic=False):
        if DLL_SHA256 != BORROWED_LAYOUT_SHA256:
            raise RuntimeError("Native delivery requires a validated borrowed layout")
        super().__init__(width, height, policy, engine)
        self.pool = None
        self.slot = None
        try:
            self.pool = LiveTexturePool(width, height, diagnostic=diagnostic)
        except BaseException:
            super().close()
            raise

    def _project(self, frame, refined):
        if type(self.slot) is not int or self.slot not in (0, 1):
            raise RuntimeError("Native producer must own a writable slot")
        self.pool.owner()
        try:
            self.pool.check(
                self.pool.dll.live_pool_publish(
                    self.pool.handle,
                    self.handle,
                    self.policy.convergence,
                    max(1.0, self.width * self.policy.divergence),
                    int(self.policy.conservative_stereo_coverage),
                    refined.ctypes.data if refined is not None else None,
                    self.slot,
                    0,
                )
            )
        except BaseException:
            self.failed = True
            raise
        self.syncs += 2  # Invalid-depth readback, then CUDA publication completion.
        self.d2h += 4
        return self.slot

    def _pack_result(self, projected):
        return projected  # Slot ID only; no CPU SBS output allocation/readback.

    def close(self):
        error = None
        if self.pool is not None:
            try:
                self.pool.close()
            except Exception as failure:
                error = failure
        try:
            super().close()
        except Exception as failure:
            if error is None:
                raise
            error.add_note(str(failure))
        if error is not None:
            raise error
