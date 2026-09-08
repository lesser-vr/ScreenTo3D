"""Model-independent depth contract; imports no TensorRT/CUDA modules."""
from dataclasses import asdict, dataclass
from typing import Callable, Protocol

import numpy as np


class DepthEngineProtocol(Protocol):
    def infer(self, tensor: np.ndarray) -> np.ndarray: ...
    def telemetry(self) -> dict: ...
    def __enter__(self): ...
    def __exit__(self, kind, value, traceback): ...


@dataclass(frozen=True)
class BackendSpec:
    model_id: str
    runtime: str
    stateful: bool = False
    requires_every_frame: bool = False
    polarity: str = 'larger_is_nearer'


@dataclass(frozen=True)
class BackendBinding:
    spec: BackendSpec
    engine_factory: Callable
    prepare: Callable
    input_validator: Callable | None = None

    def validate_policy(self, policy):
        if self.spec.polarity != 'larger_is_nearer':
            raise ValueError('Backend must adapt depth polarity to larger_is_nearer')
        if (self.spec.stateful or self.spec.requires_every_frame) and policy.inference_cadence != 1:
            raise ValueError('Selected depth backend requires inference on every frame')

    def reset(self, engine, reason):
        if reason not in ('start', 'scene_cut', 'source_change', 'discontinuity'):
            raise ValueError('Unknown depth reset reason')
        if self.spec.stateful:
            reset = getattr(engine, 'reset', None)
            if not callable(reset):
                raise TypeError('Stateful depth backend must implement reset(reason)')
            reset(reason)

    def infer(self, engine, tensor):
        depth = engine.infer(tensor)
        if (not isinstance(depth, np.ndarray) or depth.dtype != np.float32 or
                depth.ndim != 3 or depth.shape[0] != 1 or
                not all(1 <= dimension <= 8192 for dimension in depth.shape[1:]) or
                not np.isfinite(depth).all()):
            raise ValueError('Depth backend must return finite float32 [1,H,W]')
        # Own the returned buffer, including engines which recycle output memory.
        return depth.copy()

    def describe(self):
        return asdict(self.spec)


def resolve_backend(model_id, engine_factory, prepare):
    if model_id != 'da2-small':
        raise ValueError(f'Depth backend is not installed/validated: {model_id}')
    return BackendBinding(BackendSpec('da2-small', 'tensorrt'), engine_factory, prepare)


def vda_binding(directory, runtime_dir):
    from .vda_artifacts import artifact_profiles, select_artifact
    profiles = artifact_profiles(directory)
    if runtime_dir is None or not (runtime_dir / 'nvinfer_11.dll').is_file():
        raise ValueError('VDA requires an explicit TensorRT 11 runtime directory')
    # A binding belongs to one synchronous conversion job, not concurrent jobs.
    selected = next(iter(profiles.values())) if len(profiles) == 1 else None
    matched_input = False
    def validate(metadata):
        nonlocal selected, matched_input
        selected = None
        matched_input = False
        selected = select_artifact(profiles, metadata)
        matched_input = True
    def factory(progress):
        if selected is None:
            raise ValueError('VDA profile must be selected by input preflight before engine creation')
        from .vda_backend import VdaEngine
        if progress is not None:
            shape = next(shape for shape, path in profiles.items() if path == selected)
            progress({'event': 'vda_profile', 'input_shape': [1, 1, 3, *shape], 'automatic_match': matched_input})
        return VdaEngine(selected, runtime_dir, progress)
    return BackendBinding(BackendSpec('vda-small', 'tensorrt-fp32', stateful=True, requires_every_frame=True),
                          factory, lambda frame: frame, validate)
