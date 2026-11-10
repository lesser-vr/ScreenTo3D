"""Live model adapters: capabilities and lazy engine/renderer wiring in one place.

    Worker lifecycle and delivery stay model-independent. These adapters do not
    replace model-specific preprocessing, depth tokens, policies or license gates.
"""
from dataclasses import dataclass, replace
from typing import Callable


def _small_renderer(native, gpu_capture):
    if gpu_capture:
        from .live_small_gpu_input import LiveSmallGpuInput, LiveSmallGpuInputTexture
        return LiveSmallGpuInputTexture if native else LiveSmallGpuInput
    if native:
        from .live_gpu_texture import LiveGpuTexture
        return LiveGpuTexture
    from .live_gpu_candidate import LiveGpuCandidate
    return LiveGpuCandidate


def _source_renderer(native, gpu_capture):
    if native:
        from .live_source_gpu_texture import LiveSourceGpuTexture
        return LiveSourceGpuTexture
    from .live_source_gpu_candidate import LiveSourceGpuCandidate
    return LiveSourceGpuCandidate


def _small_gpu_engine(progress):
    from .small_gpu_input import SmallGpuCaptureEngine
    return SmallGpuCaptureEngine(progress)


def _small_host_io(engine, frame, depth):
    return engine.input_bytes, engine.output_bytes


def _source_host_io(engine, frame, depth):
    from math import prod
    shape = getattr(engine, 'input_shape', (1,3,*getattr(engine,'shape',frame.shape[:2])))
    return int(prod(shape)*4), depth.nbytes


@dataclass(frozen=True)
class LiveModelAdapter:
    renderer: Callable
    host_io_bytes: Callable
    gpu_capture: bool = False
    gpu_capture_engine: Callable | None = None
    rowflow: bool = False
    coalesced_history: bool = False
    short_skip_history: bool = False
    single_skip_history: bool = False
    temporal_depth_alpha: float | None = None
    stabilize_depth_range: bool = False

    def apply_live_policy(self, policy):
        return replace(policy, temporal_depth_alpha=self.temporal_depth_alpha,
                       stabilize_depth_range=self.stabilize_depth_range)

    def bind_capture(self, backend, enabled):
        if enabled and not self.gpu_capture:
            raise ValueError('Selected model does not support GPU capture')
        if enabled and self.gpu_capture_engine is not None:
            return replace(backend, engine_factory=self.gpu_capture_engine)
        return backend

    def renderer_factory(self, *, native, gpu_capture):
        if gpu_capture and not self.gpu_capture:
            raise ValueError('Selected model does not support GPU capture')
        return self.renderer(native, gpu_capture)


_MODELS = {
    'da2-small': LiveModelAdapter(_small_renderer, _small_host_io, True, _small_gpu_engine, coalesced_history=True),
    'da2-base': LiveModelAdapter(_source_renderer, _source_host_io, gpu_capture=True, rowflow=True, coalesced_history=True),
    'vda-small': LiveModelAdapter(_source_renderer, _source_host_io, gpu_capture=True, single_skip_history=True),
    'ovda-small-c16': LiveModelAdapter(_source_renderer, _source_host_io, gpu_capture=True, short_skip_history=True,
                                    temporal_depth_alpha=.5, stabilize_depth_range=True),
}


def model_adapter(model):
    try:
        return _MODELS[model]
    except (KeyError, TypeError):
        raise ValueError('Unsupported live depth model') from None
