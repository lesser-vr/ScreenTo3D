"""Read-only installation inventory in an isolated process, never engine load."""

from .messages import Message as M
from .messages import joined, message_value, payload

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
            checks.append((True, label + M(' · Verified')))
        except Exception as error:
            checks.append((False, label + " · " + message_value(error)))

    def exists(path):
        if not path.is_file():
            raise ValueError(M('File not found. Check the advanced settings.'))

    run("TensorRT", lambda: exists(Path(runtime) / "nvinfer_11.dll"))
    for tool in ("ffmpeg", "ffprobe"):
        run(tool, lambda t=tool: exists(Path(media) / (t + ".exe")))
    for package in ("numpy", "tensorrt", "cuda-bindings"):
        run(package, lambda p=package: importlib.metadata.version(p))
    if model == "da2-small":
        run("DA2 Small", lambda: exists(BUNDLE / "models/da2-small/model_fp16.onnx"))
    elif model == "da2-base":
        from .da2_base import profiles

        run(M('DA2 Base profiles'), lambda: profiles(Path(engine)))
    elif model == "vda-small":
        from .vda_artifacts import artifact_profiles

        run(M('VDA profiles'), lambda: artifact_profiles(Path(engine)))
    else:
        raise ValueError("Unknown model")
    if renderer == "cuda":
        from .local_projection import checked_dll

        run(M('CUDA stereo'), checked_dll)
    return all(ok for ok, _ in checks), joined("\n", (text for _, text in checks))


if __name__ == "__main__":
    try:
        ready, message = check(*sys.argv[1:])
        print(json.dumps({"ready": ready, "message": message, "localized": payload(message)}, ensure_ascii=False))
    except Exception as error:
        print(json.dumps({"ready": False, "message": str(error), "localized": payload(error)}, ensure_ascii=False))
