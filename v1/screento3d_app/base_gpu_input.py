"""Pinned source-checkout CUDA preprocessing, preserving Base's input contract."""
from .da2_base import content_rect
from .desktop_jobs import ROOT
from .gpu_runtime import FixedCanvasGpuInput

DLL_PATH = ROOT / 'out/base-input/base_input.dll'
DLL_SHA256 = '0af243632a9bd59e71cdca6abf0c61a44b4b73f161f86dc1d4df24897f8843cb'


class BaseGpuInput(FixedCanvasGpuInput):
    def __init__(self, engine):
        super().__init__(engine, DLL_PATH, DLL_SHA256, 'base_prepare', content_rect)

    def prepare(self, rgb, output=None):
        return super().prepare(rgb, self.engine.shape, output)
