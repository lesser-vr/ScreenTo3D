"""Native-texture boundary timing for a quality-approved rolling guide DLL."""

import argparse
import ctypes as ct
import hashlib
import json
import math
import platform
import statistics
import threading
import time
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from benchmark_live_guide_candidate import (
    frame_set,
    gpu_snapshot,
    sha256,
    timing_summary,
)
from depthsbs_app.desktop_jobs import BUNDLE
from depthsbs_app.resources import configure_resource_root


class BenchmarkTexturePool:
    """Test-only pool with a no-copy keyed-mutex consumer."""

    runtime_path = None
    runtime_hash = None

    def __init__(self, width, height, *, diagnostic=False):
        if diagnostic:
            raise ValueError("Benchmark consumer does not enable readback")
        path = self.runtime_path
        if path is None or hashlib.sha256(path.read_bytes()).hexdigest() != self.runtime_hash:
            raise ValueError("Benchmark texture runtime checksum mismatch")
        self.thread = threading.get_ident()
        self.dll = ct.CDLL(str(path))
        self.dll.live_texture_error.restype = ct.c_char_p
        self.dll.live_pool_create.argtypes = [ct.c_int] * 3
        self.dll.live_pool_create.restype = ct.c_void_p
        self.dll.live_pool_destroy.argtypes = [ct.c_void_p]
        self.dll.live_pool_publish.argtypes = [
            ct.c_void_p,
            ct.c_void_p,
            ct.c_float,
            ct.c_float,
            ct.c_int,
            ct.c_void_p,
            ct.c_int,
            ct.c_int,
        ]
        self.dll.live_pool_consume.argtypes = [ct.c_void_p, ct.c_int]
        self.handle = self.dll.live_pool_create(width, height, 0)
        self.check(self.handle)

    def check(self, code):
        if not code:
            raise RuntimeError(self.dll.live_texture_error().decode("utf-8", "replace"))

    def owner(self):
        if threading.get_ident() != self.thread or not self.handle:
            raise RuntimeError("Invalid benchmark texture-pool owner or closed pool")

    def consume(self, index):
        self.owner()
        self.check(self.dll.live_pool_consume(self.handle, index))

    def close(self):
        if threading.get_ident() != self.thread:
            raise RuntimeError("Benchmark texture pool closed from another thread")
        handle, self.handle = self.handle, None
        if handle:
            self.check(self.dll.live_pool_destroy(handle))


def create_native_candidate(
    gpu_module, texture_class, path, digest, width, height, policy, engine
):
    with (
        patch.object(gpu_module, "DLL_PATH", path),
        patch.object(gpu_module, "DLL_SHA256", digest),
    ):
        return texture_class(width, height, policy, engine)


def run_path(gpu, frames):
    guide = []
    started = time.perf_counter()
    for frame in frames:
        token = gpu.infer(frame)
        gpu.slot = gpu.frames % 2
        slot = gpu.render(frame, token)
        gpu.pool.consume(slot)
        guide.append(float(gpu.gpu_ms[5]))
    elapsed = time.perf_counter() - started
    return {"seconds": elapsed, "fps": len(frames) / elapsed, "guide_ms": guide}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-dll", type=Path, required=True)
    parser.add_argument("--runtime-dll", type=Path, required=True)
    parser.add_argument("--quality-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=("performance", "balanced", "video-quality"),
        default="balanced",
    )
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--frames-per-repeat", type=int, default=20)
    parser.add_argument("--minimum-guide-improvement-percent", type=float, default=3.0)
    parser.add_argument("--minimum-native-fps-improvement-percent", type=float, default=3.0)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    if args.repeats < 5 or args.frames_per_repeat < 20:
        raise ValueError("Native comparison requires five repeats of at least 20 frames")
    gates = (
        args.minimum_guide_improvement_percent,
        args.minimum_native_fps_improvement_percent,
    )
    if any(not math.isfinite(value) or value <= -100 for value in gates):
        raise ValueError("Improvement gates must be greater than -100 percent")

    candidate_path = args.candidate_dll.resolve()
    candidate_hash = sha256(candidate_path)
    runtime_path = args.runtime_dll.resolve()
    runtime_hash = sha256(runtime_path)
    quality_path = args.quality_report.resolve()
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    if not quality.get("passed"):
        raise ValueError("Candidate quality report did not pass")
    if quality["environment"]["candidate_dll_sha256"] != candidate_hash:
        raise ValueError("Candidate DLL differs from the quality-approved artifact")

    args.output.mkdir(parents=True)
    configure_resource_root(BUNDLE)
    import depthsbs_app.live_gpu_candidate as gpu_module
    import depthsbs_app.live_gpu_texture as texture_module
    from depthsbs_app.live_gpu_candidate import DLL_PATH, DLL_SHA256
    from depthsbs_app.live_gpu_texture import LiveGpuTexture
    from depthsbs_app.live_policy import resolve_live
    from depthsbs_app.trt_backend import DepthEngine

    BenchmarkTexturePool.runtime_path = runtime_path
    BenchmarkTexturePool.runtime_hash = runtime_hash

    report = {
        "passed": False,
        "scope": (
            f"Same-process 3840x2160 {args.mode} inference, postprocess and native "
            "CUDA/D3D11 texture publication. No full SBS readback occurs. This does "
            "not include WGC capture, worker IPC, Qt painting, display scanout, "
            "pacing, frame generation or VR acceptance."
        ),
        "acceptance": {
            "quality_report_passed": True,
            "minimum_guide_improvement_percent": args.minimum_guide_improvement_percent,
            "minimum_native_fps_improvement_percent": args.minimum_native_fps_improvement_percent,
        },
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "gpu_preflight": gpu_snapshot(),
            "current_dll": str(DLL_PATH),
            "current_dll_sha256": DLL_SHA256,
            "candidate_dll": str(candidate_path),
            "candidate_dll_sha256": candidate_hash,
            "benchmark_texture_runtime": str(runtime_path),
            "benchmark_texture_runtime_sha256": runtime_hash,
            "quality_report": str(quality_path),
            "quality_report_sha256": sha256(quality_path),
        },
        "runs": [],
    }
    try:
        width, height = 3840, 2160
        policy = resolve_live(args.mode)
        frames = frame_set(width, height, args.frames_per_repeat)
        with (
            patch.object(texture_module, "LiveTexturePool", BenchmarkTexturePool),
            DepthEngine() as engine,
            ExitStack() as scope,
        ):
            current = scope.enter_context(LiveGpuTexture(width, height, policy, engine))
            candidate = scope.enter_context(
                create_native_candidate(
                    gpu_module,
                    LiveGpuTexture,
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
            report["counters"] = {
                name: {
                    "frames": gpu.frames,
                    "h2d_bytes": gpu.h2d,
                    "d2h_bytes": gpu.d2h,
                    "synchronizations": gpu.syncs,
                    "cpu_refinements": gpu.cpu_refinements,
                }
                for name, gpu in (("current", current), ("candidate", candidate))
            }

        summaries = {}
        for name in ("current", "candidate"):
            selected = [row for row in report["runs"] if row["path"] == name]
            guide = [value for row in selected for value in row["guide_ms"]]
            summaries[name] = {
                "guide": timing_summary(guide),
                "repeat_fps": [row["fps"] for row in selected],
                "median_fps": statistics.median(row["fps"] for row in selected),
            }
        current_guide = summaries["current"]["guide"]["p50_ms"]
        candidate_guide = summaries["candidate"]["guide"]["p50_ms"]
        guide_improvement = (1 - candidate_guide / current_guide) * 100
        current_fps = summaries["current"]["median_fps"]
        candidate_fps = summaries["candidate"]["median_fps"]
        fps_improvement = (candidate_fps / current_fps - 1) * 100
        report["summary"] = {
            "size": [width, height],
            "per_eye": [width, height],
            "combined_sbs": [width * 2, height],
            "mode": args.mode,
            "radius": policy.depth_guide_radius,
            "repeats": args.repeats,
            "frames_per_repeat": args.frames_per_repeat,
            "timing": summaries,
            "guide_p50_improvement_percent": guide_improvement,
            "native_fps_improvement_percent": fps_improvement,
            "promotion_supported": guide_improvement
            >= args.minimum_guide_improvement_percent
            and fps_improvement >= args.minimum_native_fps_improvement_percent,
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
