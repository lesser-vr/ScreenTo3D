"""Matched exactness and 4K timing for an isolated live guided-filter DLL."""

import argparse
import hashlib
import json
import platform
import statistics
import subprocess
import time
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import numpy as np

from depthsbs_app.desktop_jobs import BUNDLE
from depthsbs_app.resources import configure_resource_root


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def gpu_snapshot():
    command = [
        "nvidia-smi",
        "--query-gpu=name,driver_version,utilization.gpu,memory.used,memory.free,power.draw,clocks.sm",
        "--format=csv,noheader,nounits",
    ]
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    ).stdout.strip()


def frame_set(width, height, count):
    x = np.arange(width, dtype=np.uint16)[None, :]
    y = np.arange(height, dtype=np.uint16)[:, None]
    base = np.empty((height, width, 3), np.uint8)
    base[:, :, 0] = (x + y) % 256
    base[:, :, 1] = (3 * x + 5 * y) % 256
    base[:, :, 2] = (7 * x + 2 * y) % 256
    return [np.roll(base, index * 7, axis=1) for index in range(count)]


def create_candidate(module, cls, path, digest, width, height, policy, engine):
    with (
        patch.object(module, "DLL_PATH", path),
        patch.object(module, "DLL_SHA256", digest),
    ):
        return cls(width, height, policy, engine)


def percentile(values, fraction):
    return float(np.percentile(np.asarray(values, np.float64), fraction * 100))


def timing_summary(samples):
    return {
        "samples": len(samples),
        "p50_ms": percentile(samples, 0.50),
        "p95_ms": percentile(samples, 0.95),
        "p99_ms": percentile(samples, 0.99),
        "mean_ms": statistics.fmean(samples),
    }


def run_path(gpu, frames):
    guide = []
    started = time.perf_counter()
    for frame in frames:
        token = gpu.infer(frame)
        gpu.render(frame, token)
        guide.append(float(gpu.gpu_ms[5]))
    elapsed = time.perf_counter() - started
    return {
        "seconds": elapsed,
        "fps": len(frames) / elapsed,
        "guide_ms": guide,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-dll", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--frames-per-repeat", type=int, default=8)
    parser.add_argument("--minimum-guide-improvement-percent", type=float, default=3.0)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    if args.repeats < 3 or args.frames_per_repeat < 3:
        raise ValueError("At least three repeats and frames are required")
    if args.minimum_guide_improvement_percent <= 0:
        raise ValueError("A positive guide improvement gate is required")
    candidate_path = args.candidate_dll.resolve()
    candidate_hash = sha256(candidate_path)
    args.output.mkdir(parents=True)
    configure_resource_root(BUNDLE)

    import depthsbs_app.live_gpu_candidate as gpu_module
    from depthsbs_app.live_gpu_candidate import (
        DLL_PATH,
        DLL_SHA256,
        LiveGpuCandidate,
    )
    from depthsbs_app.live_policy import resolve_live
    from depthsbs_app.trt_backend import DepthEngine

    report = {
        "scope": (
            "Same-process current-versus-isolated-DLL comparison. Host SBS readback "
            "is retained equally; CUDA event guide intervals are the primary timing. "
            "This is not integrated live capture, physical display or VR acceptance."
        ),
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "gpu_preflight": gpu_snapshot(),
            "current_dll": str(DLL_PATH),
            "current_dll_sha256": DLL_SHA256,
            "candidate_dll": str(candidate_path),
            "candidate_dll_sha256": candidate_hash,
            "source_sha256": sha256(Path("experiments/cuda_projection/live_depth.cu")),
        },
        "parity": [],
        "runs": [],
        "acceptance": {
            "depth_bits_exact": True,
            "sbs_rgb_exact": True,
            "minimum_guide_improvement_percent": args.minimum_guide_improvement_percent,
        },
    }
    try:
        with DepthEngine() as engine:
            for width, height in ((16, 16), (127, 69), (640, 360)):
                parity_frames = frame_set(width, height, 3)
                for mode in ("performance", "balanced", "video-quality"):
                    policy = resolve_live(mode)
                    with ExitStack() as scope:
                        current = scope.enter_context(
                            LiveGpuCandidate(width, height, policy, engine)
                        )
                        candidate = scope.enter_context(
                            create_candidate(
                                gpu_module,
                                LiveGpuCandidate,
                                candidate_path,
                                candidate_hash,
                                width,
                                height,
                                policy,
                                engine,
                            )
                        )
                        for index, frame in enumerate(parity_frames):
                            expected, expected_depth = current.render(
                                frame, current.infer(frame), diagnostic=True
                            )
                            actual, actual_depth = candidate.render(
                                frame, candidate.infer(frame), diagnostic=True
                            )
                            depth_bits_exact = bool(
                                np.array_equal(
                                    expected_depth.view(np.uint32),
                                    actual_depth.view(np.uint32),
                                )
                            )
                            rgb_exact = bool(np.array_equal(expected, actual))
                            report["parity"].append(
                                {
                                    "size": f"{width}x{height}",
                                    "mode": mode,
                                    "radius": policy.depth_guide_radius,
                                    "frame": index,
                                    "depth_bits_exact": depth_bits_exact,
                                    "sbs_rgb_exact": rgb_exact,
                                    "passed": depth_bits_exact and rgb_exact,
                                }
                            )

            width, height = 3840, 2160
            frames = frame_set(width, height, args.frames_per_repeat)
            policy = resolve_live("balanced")
            with ExitStack() as scope:
                current = scope.enter_context(
                    LiveGpuCandidate(width, height, policy, engine)
                )
                candidate = scope.enter_context(
                    create_candidate(
                        gpu_module,
                        LiveGpuCandidate,
                        candidate_path,
                        candidate_hash,
                        width,
                        height,
                        policy,
                        engine,
                    )
                )
                run_path(current, frames[:3])
                run_path(candidate, frames[:3])
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
                                {
                                    "path": name,
                                    "repeat": repeat,
                                    "fps": result["fps"],
                                    "guide_p50_ms": statistics.median(
                                        result["guide_ms"]
                                    ),
                                }
                            ),
                            flush=True,
                        )

        summaries = {}
        for name in ("current", "candidate"):
            selected = [row for row in report["runs"] if row["path"] == name]
            guide = [value for row in selected for value in row["guide_ms"]]
            summaries[name] = {
                "guide": timing_summary(guide),
                "repeat_fps": [row["fps"] for row in selected],
                "median_fps": statistics.median(row["fps"] for row in selected),
            }
        current_p50 = summaries["current"]["guide"]["p50_ms"]
        candidate_p50 = summaries["candidate"]["guide"]["p50_ms"]
        improvement = (1 - candidate_p50 / current_p50) * 100
        report["summary"] = {
            "parity_cases": len(report["parity"]),
            "parity_passed": all(row["passed"] for row in report["parity"]),
            "timing": summaries,
            "guide_p50_change_percent": (candidate_p50 / current_p50 - 1) * 100,
            "guide_p50_improvement_percent": improvement,
            "promotion_supported": all(row["passed"] for row in report["parity"])
            and improvement >= args.minimum_guide_improvement_percent,
        }
        report["environment"]["gpu_postflight"] = gpu_snapshot()
        report["passed"] = report["summary"]["parity_passed"]
        return 0 if report["passed"] else 1
    finally:
        (args.output / "report.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    raise SystemExit(main())
