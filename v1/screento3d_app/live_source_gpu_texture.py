"""Source-resolution device depth with native shared-texture delivery."""

from .live_gpu_texture import TextureOutputMixin
from .live_source_gpu_candidate import LiveSourceGpuCandidate


class LiveSourceGpuTexture(TextureOutputMixin, LiveSourceGpuCandidate):
    """Base/VDA/oVDA device depth with the validated native output boundary."""
