"""Alternating unpaced native-boundary gate for page-locked RGB staging."""

import argparse
import json
import math
import platform
import statistics
import time
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import numpy as np

from benchmark_live_guide_candidate import frame_set, gpu_snapshot, sha256
from benchmark_live_guide_rolling_native import BenchmarkTexturePool
from screento3d_app.desktop_jobs import BUNDLE
from screento3d_app.resources import configure_resource_root


def summarize(values):
    return {
        "samples": len(values),
        "p50_ms": float(np.percentile(values, 50)),
        "p95_ms": float(np.percentile(values, 95)),
        "mean_ms": float(np.mean(values)),
    }


def run_path(gpu, frames):
    stages = {name: [] for name in ("input_stage", "inference", "rgb_h2d", "guide")}
    started = time.perf_counter()
    for frame in frames:
        token = gpu.infer(frame)
        gpu.slot = gpu.frames % 2
        slot = gpu.render(frame, token)
        gpu.pool.consume(slot)
        stages["input_stage"].append(float(gpu.last.get("input_stage_ms", 0)))
        stages["inference"].append(float(gpu.gpu_ms[1]))
        stages["rgb_h2d"].append(float(gpu.gpu_ms[2]))
        stages["guide"].append(float(gpu.gpu_ms[5]))
    elapsed = time.perf_counter() - started
    return {"seconds": elapsed, "fps": len(frames) / elapsed, "stages_ms": stages}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dll", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--frames-per-repeat", type=int, default=20)
    parser.add_argument("--minimum-rgb-h2d-improvement-percent", type=float, default=20)
    parser.add_argument("--minimum-native-fps-improvement-percent", type=float, default=3)
    parser.add_argument("--maximum-guide-regression-percent", type=float, default=1)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    if args.repeats < 5 or args.frames_per_repeat < 20:
        raise ValueError("Pinned input comparison requires five repeats of 20 frames")
    gates = (
        args.minimum_rgb_h2d_improvement_percent,
        args.minimum_native_fps_improvement_percent,
        args.maximum_guide_regression_percent,
    )
    if any(not math.isfinite(value) or value < 0 for value in gates):
        raise ValueError("Pinned input gates must be finite and non-negative")

    runtime_path = args.runtime_dll.resolve()
    runtime_hash = sha256(runtime_path)
    args.output.mkdir(parents=True)
    configure_resource_root(BUNDLE)
    import screento3d_app.live_gpu_texture as texture_module
    from screento3d_app.live_gpu_candidate import DLL_PATH, DLL_SHA256
    from screento3d_app.live_gpu_texture import LiveGpuTexture
    from screento3d_app.live_pinned_input import LiveGpuPinnedTexture
    from screento3d_app.live_policy import resolve_live
    from screento3d_app.trt_backend import DepthEngine

    BenchmarkTexturePool.runtime_path = runtime_path
    BenchmarkTexturePool.runtime_hash = runtime_hash
    report = {
        "passed": False,
        "scope": (
            "Same-process unpaced 3840x2160 Balanced inference, CUDA postprocess, "
            "native texture publication and no-copy keyed-mutex consumption. It "
            "excludes WGC, IPC, Qt, physical display, pacing and VR acceptance."
        ),
        "acceptance": {
            "minimum_rgb_h2d_improvement_percent": args.minimum_rgb_h2d_improvement_percent,
            "minimum_native_fps_improvement_percent": args.minimum_native_fps_improvement_percent,
            "maximum_guide_regression_percent": args.maximum_guide_regression_percent,
        },
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "gpu_preflight": gpu_snapshot(),
            "product_dll": str(DLL_PATH),
            "product_dll_sha256": DLL_SHA256,
            "runtime_dll": str(runtime_path),
            "runtime_dll_sha256": runtime_hash,
            "candidate_source_sha256": sha256(
                Path("v1/screento3d_app/live_pinned_input.py")
            ),
        },
        "runs": [],
    }
    try:
        width, height = 3840, 2160
        frames = frame_set(width, height, args.frames_per_repeat)
        policy = resolve_live("balanced")
        with (
            patch.object(texture_module, "LiveTexturePool", BenchmarkTexturePool),
            DepthEngine() as engine,
            ExitStack() as scope,
        ):
            current = scope.enter_context(
                LiveGpuTexture(width, height, policy, engine)
            )
            candidate = scope.enter_context(
                LiveGpuPinnedTexture(width, height, policy, engine)
            )
            run_path(current, frames[:5])
            run_path(candidate, frames[:5])
            for repeat in range(args.repeats):
                order = (
                    (("current", current), ("candidate", candidate))
                    if repeat % 2 == 0
                    else (("candidate", candidate), ("current", current))
                )
                for name, gpu in order:
                    gpu.reset()
                    result = run_path(gpu, frames)
                    result.update(path=name, repeat=repeat, order=order[0][0])
                    report["runs"].append(result)
                    print(
                        json.dumps(
                            {"path": name, "repeat": repeat, "fps": result["fps"]}
                        ),
                        flush=True,
                    )
            report["counters"] = {
                name: {
                    "frames": gpu.frames,
                    "h2d_bytes": gpu.h2d,
                    "d2h_bytes": gpu.d2h,
                    "synchronizations": gpu.syncs,
                    "pinned_input_bytes": (
                        gpu.pinned_input.size if name == "candidate" else 0
                    ),
                }
                for name, gpu in (("current", current), ("candidate", candidate))
            }

        summary = {}
        for name in ("current", "candidate"):
            selected = [row for row in report["runs"] if row["path"] == name]
            summary[name] = {
                "repeat_fps": [row["fps"] for row in selected],
                "median_fps": statistics.median(row["fps"] for row in selected),
                "stages_ms": {
                    stage: summarize(
                        [value for row in selected for value in row["stages_ms"][stage]]
                    )
                    for stage in selected[0]["stages_ms"]
                },
            }
        current_h2d = summary["current"]["stages_ms"]["rgb_h2d"]["p50_ms"]
        candidate_h2d = summary["candidate"]["stages_ms"]["rgb_h2d"]["p50_ms"]
        h2d_improvement = (1 - candidate_h2d / current_h2d) * 100
        current_fps = summary["current"]["median_fps"]
        candidate_fps = summary["candidate"]["median_fps"]
        fps_improvement = (candidate_fps / current_fps - 1) * 100
        current_guide = summary["current"]["stages_ms"]["guide"]["p50_ms"]
        candidate_guide = summary["candidate"]["stages_ms"]["guide"]["p50_ms"]
        guide_regression = (candidate_guide / current_guide - 1) * 100
        report["summary"] = {
            "size": [width, height],
            "per_eye": [width, height],
            "combined_sbs": [width * 2, height],
            "mode": "balanced",
            "repeats": args.repeats,
            "frames_per_repeat": args.frames_per_repeat,
            "timing": summary,
            "rgb_h2d_p50_improvement_percent": h2d_improvement,
            "native_fps_improvement_percent": fps_improvement,
            "guide_p50_regression_percent": guide_regression,
        }
        report["passed"] = (
            h2d_improvement >= args.minimum_rgb_h2d_improvement_percent
            and fps_improvement >= args.minimum_native_fps_improvement_percent
            and guide_regression <= args.maximum_guide_regression_percent
        )
        report["environment"]["gpu_postflight"] = gpu_snapshot()
        return 0 if report["passed"] else 1
    finally:
        (args.output / "report.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    raise SystemExit(main())
