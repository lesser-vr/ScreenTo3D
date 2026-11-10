"""Model-defined live backend selection with no implicit fallback."""
from .messages import ErrorMessage as E


from pathlib import Path

from .config import DEFAULT_MODE_MODELS, MODE_MODEL_CHOICES, MODES, validate_mode_model


def choices(mode):
    if mode == "offline-quality":
        raise ValueError(E('E_LIVE_OFFLINE_MODE'))
    if mode not in MODE_MODEL_CHOICES:
        raise ValueError(E('E_LIVE_MODE_INVALID'))
    return MODE_MODEL_CHOICES[mode]


def default_model(mode):
    choices(mode)
    return DEFAULT_MODE_MODELS[mode]


def validate_snapshot(snapshot, mode):
    if not isinstance(snapshot, dict):
        raise ValueError(E('E_LIVE_MODEL_MISSING'))
    model = snapshot.get("model")
    validate_mode_model(mode, model)
    if model not in choices(mode):
        raise ValueError(E('E_LIVE_MODEL_MISMATCH'))
    runtime = snapshot.get("runtime")
    engine = snapshot.get("engine")
    noncommercial = snapshot.get("noncommercial", False)
    if type(noncommercial) is not bool:
        raise ValueError(E('E_MODEL_LICENSE_INVALID'))
    if model != "da2-small":
        if not isinstance(engine, str) or not engine:
            raise ValueError(E('E_LIVE_MODEL_PATH_INVALID'))
        if not isinstance(runtime, str) or not runtime:
            raise ValueError(E('E_LIVE_TENSORRT_PATH_INVALID'))
    if model == "ovda-small-c16" and not noncommercial:
        raise ValueError(E('E_LIVE_OVDA_LICENSE_REQUIRED'))
    return {
        "model": model,
        "engine": engine or "",
        "runtime": runtime or "",
        "noncommercial": noncommercial,
    }


def binding(snapshot, mode, metadata, da2_engine_factory, da2_prepare):
    selected = validate_snapshot(snapshot, mode)
    model = selected["model"]
    if model == "da2-small":
        from .depth_backend import resolve_backend

        result = resolve_backend(model, da2_engine_factory, da2_prepare)
    elif model == "da2-base":
        from .da2_base import binding as create

        result = create(Path(selected["engine"]), Path(selected["runtime"]), device_depth=True)
    elif model == "vda-small":
        from .depth_backend import vda_binding

        result = vda_binding(
            Path(selected["engine"]),
            Path(selected["runtime"]),
            device_depth=True,
        )
    elif model == "ovda-small-c16":
        from .ovda import binding as create

        result = create(
            Path(selected["engine"]),
            Path(selected["runtime"]),
            selected["noncommercial"],
            device_depth=True,
        )
    else:  # validate_snapshot owns the public model set.
        raise ValueError(E('E_LIVE_MODEL_UNSUPPORTED'))
    if result.input_validator is not None:
        result.input_validator(metadata)
    result.validate_policy(MODES[mode])
    return result
