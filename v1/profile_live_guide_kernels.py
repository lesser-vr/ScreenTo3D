"""Exact diagnostic decomposition of the current live guided-filter CUDA stage."""

import argparse
import ctypes as ct
import json
import statistics
import time
from contextlib import ExitStack
from pathlib import Path

import numpy as np

from benchmark_live_guide_candidate import (
    create_candidate,
    frame_set,
    gpu_snapshot,
    sha256,
    timing_summary,
)
from depthsbs_app.desktop_jobs import BUNDLE
from depthsbs_app.resources import configure_resource_root


SUBKERNELS = ("moments_x", "coefficients_y", "coefficients_x", "guided_y")


def bind_profile(gpu):
    gpu.dll.live_guide_times.argtypes = [ct.c_void_p, ct.c_void_p]


def run_path(gpu, frames, *, profile=False):
    guide = []
    subkernels = []
    sum_errors = []
    output = np.zeros(4, np.float32)
    started = time.perf_counter()
    for frame in frames:
        gpu.render(frame, gpu.infer(frame))
        total = float(gpu.gpu_ms[5])
        guide.append(total)
        if profile:
            gpu._check(gpu.dll.live_guide_times(gpu.handle, output.ctypes.data))
            values = [float(value) for value in output]
            subkernels.append(values)
            sum_errors.append(abs(sum(values) - total))
    elapsed = time.perf_counter() - started
    return {
        "seconds": elapsed,
        "fps": len(frames) / elapsed,
        "guide_ms": guide,
        "subkernel_ms": subkernels,
        "subkernel_sum_error_ms": sum_errors,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile-dll", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--frames-per-repeat", type=int, default=20)
    parser.add_argument("--max-instrumentation-overhead-percent", type=float, default=3)
    parser.add_argument("--max-event-sum-error-ms", type=float, default=0.02)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    if args.repeats < 3 or args.frames_per_repeat < 3:
        raise ValueError("At least three repeats and frames are required")
    if (
        args.max_instrumentation_overhead_percent <= 0
        or args.max_event_sum_error_ms <= 0
    ):
        raise ValueError("Positive instrumentation gates are required")
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

    profile_path = args.profile_dll.resolve()
    profile_hash = sha256(profile_path)
    report = {
        "scope": (
            "Diagnostic same-process decomposition of the current global-memory "
            "guided filter. Full host SBS output is equal on both paths and is not "
            "a live-capture, scanout, utilization or VR measurement."
        ),
        "acceptance": {
            "depth_bits_exact": True,
            "sbs_rgb_exact": True,
            "max_instrumentation_overhead_percent": args.max_instrumentation_overhead_percent,
            "max_event_sum_error_ms": args.max_event_sum_error_ms,
        },
        "environment": {
            "gpu_preflight": gpu_snapshot(),
            "current_dll": str(DLL_PATH),
            "current_dll_sha256": DLL_SHA256,
            "profile_dll": str(profile_path),
            "profile_dll_sha256": profile_hash,
            "canonical_source_sha256": sha256(
                Path("experiments/cuda_projection/live_depth.cu")
            ),
            "profile_source_sha256": sha256(
                Path("experiments/cuda_projection/live_depth_guide_profile.cu")
            ),
        },
        "parity": [],
        "runs": [],
    }
    try:
        with DepthEngine() as engine:
            for width, height in ((16, 16), (127, 69), (640, 360)):
                frames = frame_set(width, height, 3)
                for mode in ("performance", "balanced", "video-quality"):
                    policy = resolve_live(mode)
                    with ExitStack() as scope:
                        current = scope.enter_context(
                            LiveGpuCandidate(width, height, policy, engine)
                        )
                        profile = scope.enter_context(
                            create_candidate(
                                gpu_module,
                                LiveGpuCandidate,
                                profile_path,
                                profile_hash,
                                width,
                                height,
                                policy,
                                engine,
                            )
                        )
                        bind_profile(profile)
                        for index, frame in enumerate(frames):
                            expected, expected_depth = current.render(
                                frame, current.infer(frame), diagnostic=True
                            )
                            actual, actual_depth = profile.render(
                                frame, profile.infer(frame), diagnostic=True
                            )
                            depth_exact = bool(
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
                                    "depth_bits_exact": depth_exact,
                                    "sbs_rgb_exact": rgb_exact,
                                    "passed": depth_exact and rgb_exact,
                                }
                            )

            width, height = 3840, 2160
            frames = frame_set(width, height, args.frames_per_repeat)
            policy = resolve_live("balanced")
            with ExitStack() as scope:
                current = scope.enter_context(
                    LiveGpuCandidate(width, height, policy, engine)
                )
                profile = scope.enter_context(
                    create_candidate(
                        gpu_module,
                        LiveGpuCandidate,
                        profile_path,
                        profile_hash,
                        width,
                        height,
                        policy,
                        engine,
                    )
                )
                bind_profile(profile)
                run_path(current, frames[:5])
                run_path(profile, frames[:5], profile=True)
                for repeat in range(args.repeats):
                    order = (
                        (("current", current, False), ("profile", profile, True))
                        if repeat % 2 == 0
                        else (("profile", profile, True), ("current", current, False))
                    )
                    for name, gpu, instrumented in order:
                        gpu.reset()
                        result = run_path(gpu, frames, profile=instrumented)
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
        for name in ("current", "profile"):
            selected = [row for row in report["runs"] if row["path"] == name]
            guide = [value for row in selected for value in row["guide_ms"]]
            summaries[name] = {
                "guide": timing_summary(guide),
                "repeat_fps": [row["fps"] for row in selected],
                "median_fps": statistics.median(row["fps"] for row in selected),
            }
        profile_rows = [
            values
            for row in report["runs"]
            if row["path"] == "profile"
            for values in row["subkernel_ms"]
        ]
        kernel_summary = {
            name: timing_summary([row[index] for row in profile_rows])
            for index, name in enumerate(SUBKERNELS)
        }
        ranked = sorted(
            (
                {"kernel": name, "p50_ms": values["p50_ms"]}
                for name, values in kernel_summary.items()
            ),
            key=lambda row: row["p50_ms"],
            reverse=True,
        )
        sum_errors = [
            value
            for row in report["runs"]
            if row["path"] == "profile"
            for value in row["subkernel_sum_error_ms"]
        ]
        current_p50 = summaries["current"]["guide"]["p50_ms"]
        profile_p50 = summaries["profile"]["guide"]["p50_ms"]
        overhead = (profile_p50 / current_p50 - 1) * 100
        parity = all(row["passed"] for row in report["parity"])
        valid = (
            parity
            and overhead <= args.max_instrumentation_overhead_percent
            and max(sum_errors) <= args.max_event_sum_error_ms
        )
        report["summary"] = {
            "parity_cases": len(report["parity"]),
            "parity_passed": parity,
            "timing": summaries,
            "instrumentation_overhead_percent": overhead,
            "subkernels": kernel_summary,
            "ranked_p50": ranked,
            "largest_subkernel": ranked[0]["kernel"],
            "event_sum_error_max_ms": max(sum_errors),
            "valid": valid,
        }
        report["environment"]["gpu_postflight"] = gpu_snapshot()
        report["passed"] = valid
        return 0 if valid else 1
    finally:
        (args.output / "report.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    raise SystemExit(main())
