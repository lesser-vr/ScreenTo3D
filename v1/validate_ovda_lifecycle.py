"""Actual oVDA lifecycle checks on the pinned public default corpus."""

import argparse
import hashlib
import json
import time
from pathlib import Path

import cv2
from screento3d_app.config import MODES
from screento3d_app.ovda import LICENSE_NOTICE, binding
from public_test_media import ATTRIBUTION, CORPUS, PublicFrames

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME = Path("C:/TensorRT/TensorRT-11.2.1.2/bin")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--noncommercial", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--engine-dir", type=Path, default=ROOT / "out/ovda-local")
    parser.add_argument("--runtime-dir", type=Path, default=DEFAULT_RUNTIME)
    args = parser.parse_args()
    if not args.noncommercial:
        raise ValueError(LICENSE_NOTICE)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite lifecycle report: {output}")

    source_path = CORPUS / "FloorballGame.mp4"
    first, second = PublicFrames("FloorballGame", 2)
    smaller = cv2.resize(first, (1280, 720), interpolation=cv2.INTER_AREA)
    backend = binding(args.engine_dir, args.runtime_dir, True)
    backend.input_validator({"width": 1920, "height": 1080})
    cadence_rejected = False
    try:
        backend.validate_policy(MODES["performance"])
    except ValueError:
        cadence_rejected = True

    started = time.perf_counter()
    events = []
    with backend.engine_factory(events.append) as engine:
        backend.reset(engine, "start")
        first_depth = backend.infer(engine, first)
        second_depth = backend.infer(engine, second)
        retained = engine.telemetry()
        if retained["cache_used"] != 2:
            raise RuntimeError("oVDA temporal cache did not retain sequential frames")

        backend.reset(engine, "scene_cut")
        cleared = engine.telemetry()
        if cleared["cache_used"] != 0:
            raise RuntimeError("oVDA scene-cut reset retained cache state")
        cut_depth = backend.infer(engine, second)

        backend.reset(engine, "discontinuity")
        small_depth = backend.infer(engine, smaller)
        backend.reset(engine, "source_change")
        restored_depth = backend.infer(engine, first)
        final = engine.telemetry()

    geometry_without_reset_rejected = False
    with backend.engine_factory(None) as engine:
        backend.reset(engine, "start")
        backend.infer(engine, first)
        try:
            backend.infer(engine, smaller)
        except ValueError as error:
            if "Reset before geometry change" not in str(error):
                raise
            geometry_without_reset_rejected = True

    expected_shapes = (
        first_depth.shape,
        second_depth.shape,
        cut_depth.shape,
        small_depth.shape,
        restored_depth.shape,
    )
    if expected_shapes != (
        (1, 1080, 1920),
        (1, 1080, 1920),
        (1, 1080, 1920),
        (1, 720, 1280),
        (1, 1080, 1920),
    ):
        raise RuntimeError(f"Unexpected oVDA output geometry: {expected_shapes}")
    if not cadence_rejected or not geometry_without_reset_rejected:
        raise RuntimeError("oVDA lifecycle rejection contract failed")

    report = {
        "passed": True,
        "scope": (
            "Actual RTX/TensorRT oVDA c16 lifecycle check using only pinned public "
            "UVG-VCM frames. Not a quality, sustained-performance, leak, or release claim."
        ),
        "license": LICENSE_NOTICE,
        "attribution": ATTRIBUTION,
        "source": str(source_path.resolve()),
        "source_sha256": sha256(source_path),
        "events": events,
        "sequential_cache_used": retained["cache_used"],
        "scene_cut_cache_used_after_reset": cleared["cache_used"],
        "cadence_rejected": cadence_rejected,
        "geometry_without_reset_rejected": geometry_without_reset_rejected,
        "output_shapes": [list(shape) for shape in expected_shapes],
        "final_engine": final,
        "elapsed_seconds": time.perf_counter() - started,
        "source_hashes": {
            name: sha256(ROOT / name)
            for name in (
                "v1/validate_ovda_lifecycle.py",
                "v1/screento3d_app/ovda.py",
                "experiments/ovda/trt_engine.py",
                "v1/public_test_media.py",
            )
        },
    }
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(output), "passed": True}, indent=2))


if __name__ == "__main__":
    main()
