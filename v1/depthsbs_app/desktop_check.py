"""Read-only installation inventory in an isolated process, never engine load."""

import importlib.metadata
import json
import sys
from pathlib import Path

from .desktop_jobs import BUNDLE


def check(model, engine, runtime, media, renderer):
    if model == "ovda-small-c16":
        from .ovda_installation import installation_report, summary

        report = installation_report(Path(engine), Path(runtime), Path(media), renderer)
        return report["ready"], summary(report)
    checks = []

    def run(label, action):
        try:
            action()
            checks.append((True, label + " · 확인됨"))
        except Exception as error:
            checks.append((False, label + " · " + str(error)))

    def exists(path):
        if not path.is_file():
            raise ValueError("파일이 없습니다. 고급 설정을 확인하세요.")

    run("TensorRT", lambda: exists(Path(runtime) / "nvinfer_11.dll"))
    for tool in ("ffmpeg", "ffprobe"):
        run(tool, lambda t=tool: exists(Path(media) / (t + ".exe")))
    for package in ("numpy", "tensorrt", "cuda-bindings"):
        run(package, lambda p=package: importlib.metadata.version(p))
    if model == "da2-small":
        run("DA2 Small", lambda: exists(BUNDLE / "models/da2-small/model_fp16.onnx"))
    elif model == "da2-base":
        from .da2_base import profiles

        run("DA2 Base 프로필", lambda: profiles(Path(engine)))
    elif model == "vda-small":
        from .vda_artifacts import artifact_profiles

        run("VDA 프로필", lambda: artifact_profiles(Path(engine)))
    else:
        raise ValueError("Unknown model")
    if renderer == "cuda":
        from .local_projection import checked_dll

        run("CUDA 스테레오", checked_dll)
    return all(ok for ok, _ in checks), "\n".join(text for _, text in checks)


if __name__ == "__main__":
    try:
        ready, message = check(*sys.argv[1:])
        print(json.dumps({"ready": ready, "message": message}, ensure_ascii=False))
    except Exception as error:
        print(json.dumps({"ready": False, "message": str(error)}, ensure_ascii=False))
