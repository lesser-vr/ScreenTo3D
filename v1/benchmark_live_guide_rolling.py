"""4K timing gate for a quality-approved rolling-window guide candidate."""

import argparse
import json
import platform
import statistics
from contextlib import ExitStack
from pathlib import Path

from benchmark_live_guide_candidate import (
    create_candidate,
    frame_set,
    gpu_snapshot,
    run_path,
    sha256,
    timing_summary,
)
from screento3d_app.desktop_jobs import BUNDLE
from screento3d_app.resources import configure_resource_root


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-dll", type=Path, required=True)
    parser.add_argument("--quality-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--frames-per-repeat", type=int, default=20)
    parser.add_argument("--minimum-guide-improvement-percent", type=float, default=3.0)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    if args.repeats < 3 or args.frames_per_repeat < 10:
        raise ValueError("At least three repeats and ten frames are required")
    if args.minimum_guide_improvement_percent <= 0:
        raise ValueError("A positive improvement gate is required")

    candidate_path = args.candidate_dll.resolve()
    candidate_hash = sha256(candidate_path)
    quality_path = args.quality_report.resolve()
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    if not quality.get("passed"):
        raise ValueError("Candidate quality report did not pass")
    if quality["environment"]["candidate_dll_sha256"] != candidate_hash:
        raise ValueError("Candidate DLL differs from the quality-approved artifact")

    args.output.mkdir(parents=True)
    configure_resource_root(BUNDLE)
    import screento3d_app.live_gpu_candidate as gpu_module
    from screento3d_app.live_gpu_candidate import (
        DLL_PATH,
        DLL_SHA256,
        LiveGpuCandidate,
    )
    from screento3d_app.live_policy import resolve_live
    from screento3d_app.trt_backend import DepthEngine

    report = {
        "passed": False,
        "scope": (
            "Same-process 3840x2160 Balanced comparison after the separate bounded "
            "numerical gate passed. CUDA event guide intervals are primary. Host SBS "
            "readback is retained equally. This is not integrated capture, scanout, "
            "GPU utilization, sustained 60 FPS or VR acceptance."
        ),
        "acceptance": {
            "quality_report_passed": True,
            "minimum_guide_improvement_percent": args.minimum_guide_improvement_percent,
        },
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "gpu_preflight": gpu_snapshot(),
            "current_dll": str(DLL_PATH),
            "current_dll_sha256": DLL_SHA256,
            "candidate_dll": str(candidate_path),
            "candidate_dll_sha256": candidate_hash,
            "quality_report": str(quality_path),
            "quality_report_sha256": sha256(quality_path),
            "quality_case_count": quality["summary"]["case_count"],
        },
        "runs": [],
    }
    try:
        width, height = 3840, 2160
        frames = frame_set(width, height, args.frames_per_repeat)
        policy = resolve_live("balanced")
        with DepthEngine() as engine, ExitStack() as scope:
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
                            {
                                "path": name,
                                "repeat": repeat,
                                "fps": result["fps"],
                                "guide_p50_ms": statistics.median(result["guide_ms"]),
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
            "size": [width, height],
            "mode": "balanced",
            "radius": policy.depth_guide_radius,
            "repeats": args.repeats,
            "frames_per_repeat": args.frames_per_repeat,
            "timing": summaries,
            "guide_p50_change_percent": (candidate_p50 / current_p50 - 1) * 100,
            "guide_p50_improvement_percent": improvement,
            "promotion_supported": improvement
            >= args.minimum_guide_improvement_percent,
        }
        report["passed"] = report["summary"]["promotion_supported"]
        report["environment"]["gpu_postflight"] = gpu_snapshot()
        return 0 if report["passed"] else 1
    finally:
        (args.output / "report.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    raise SystemExit(main())
