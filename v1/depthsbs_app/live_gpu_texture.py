"""Explicit native delivery; identical inherited postprocessing and mode policy."""

from .live_gpu_candidate import LiveGpuCandidate
from .live_texture_pool import LiveTexturePool

BORROWED_LAYOUT_SHA256 = (
    "0394a7b790c92db37aaa49190e213edc65914e79625f03d38d62cf3c2911da85"
)


class TextureOutputMixin:
    """Replace only the inherited host SBS output with the shared texture pool."""

    borrowed_layout_sha256 = BORROWED_LAYOUT_SHA256

    def __init__(self, width, height, policy, engine, *, diagnostic=False):
        if self.library_sha256 != self.borrowed_layout_sha256:
            raise RuntimeError("Native delivery requires a validated borrowed layout")
        self.pool = None
        self.slot = None
        super().__init__(width, height, policy, engine)
        try:
            self.pool = LiveTexturePool(width, height, diagnostic=diagnostic, layout=policy.stereo_layout)
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
                    self.stereo_convergence,
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


class LiveGpuTexture(TextureOutputMixin, LiveGpuCandidate):
    """DA2 Small device depth with native shared-texture delivery."""
