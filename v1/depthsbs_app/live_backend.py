"""Model-defined live backend selection with no implicit fallback."""

from pathlib import Path

from .config import DEFAULT_MODE_MODELS, MODE_MODEL_CHOICES, MODES, validate_mode_model


def choices(mode):
    if mode == "offline-quality":
        raise ValueError("Offline Quality는 파일 전용입니다.")
    if mode not in MODE_MODEL_CHOICES:
        raise ValueError("지원하지 않는 실시간 모드입니다.")
    return MODE_MODEL_CHOICES[mode]


def default_model(mode):
    choices(mode)
    return DEFAULT_MODE_MODELS[mode]


def validate_snapshot(snapshot, mode):
    if not isinstance(snapshot, dict):
        raise ValueError("실시간 모델 설정이 없습니다.")
    model = snapshot.get("model")
    validate_mode_model(mode, model)
    if model not in choices(mode):
        raise ValueError("실시간 모드와 깊이 모델이 일치하지 않습니다.")
    runtime = snapshot.get("runtime")
    engine = snapshot.get("engine")
    noncommercial = snapshot.get("noncommercial", False)
    if type(noncommercial) is not bool:
        raise ValueError("모델 라이선스 확인 값이 올바르지 않습니다.")
    if model != "da2-small":
        if not isinstance(engine, str) or not engine:
            raise ValueError("선택한 실시간 모델의 설치 폴더를 확인하세요.")
        if not isinstance(runtime, str) or not runtime:
            raise ValueError("TensorRT 실행 환경을 확인하세요.")
    if model == "ovda-small-c16" and not noncommercial:
        raise ValueError("oVDA의 개인·비상업적 사용 및 라이선스 조건을 확인하세요.")
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

        result = create(Path(selected["engine"]), Path(selected["runtime"]))
    elif model == "vda-small":
        from .depth_backend import vda_binding

        result = vda_binding(Path(selected["engine"]), Path(selected["runtime"]))
    elif model == "ovda-small-c16":
        from .ovda import binding as create

        result = create(
            Path(selected["engine"]),
            Path(selected["runtime"]),
            selected["noncommercial"],
        )
    else:  # validate_snapshot owns the public model set.
        raise ValueError("지원하지 않는 실시간 깊이 모델입니다.")
    if result.input_validator is not None:
        result.input_validator(metadata)
    result.validate_policy(MODES[mode])
    return result
