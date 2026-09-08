"""Bounded numerical gate for the isolated rolling-window guide candidate."""

import argparse
import hashlib
import json
import platform
import subprocess
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from depthsbs_app.desktop_jobs import BUNDLE
from depthsbs_app.resources import configure_resource_root


LIMITS = {
    "depth_mae": 1e-6,
    "depth_max": 1e-4,
    "rgb_mae": 0.05,
    "rgb_changed_fraction": 0.001,
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def gpu_snapshot():
    return subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=name,driver_version,utilization.gpu,memory.used,memory.free",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True,
        text=True,
        check=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    ).stdout.strip()


def synthetic_frames(width, height):
    x = np.arange(width, dtype=np.uint16)[None, :]
    y = np.arange(height, dtype=np.uint16)[:, None]
    base = np.empty((height, width, 3), np.uint8)
    base[:, :, 0] = (x + y) % 256
    base[:, :, 1] = (3 * x + 5 * y) % 256
    base[:, :, 2] = (7 * x + 2 * y) % 256
    frames = [np.roll(base, index * 3, axis=1) for index in range(5)]
    frames[3] = 255 - frames[3]
    return frames


def temporal_change(current, previous):
    return float(
        np.mean(
            np.abs(current.astype(np.int16) - previous.astype(np.int16)),
            dtype=np.float64,
        )
        / 255
    )


def create_candidate(module, cls, path, digest, width, height, policy, engine):
    with (
        patch.object(module, "DLL_PATH", path),
        patch.object(module, "DLL_SHA256", digest),
    ):
        return cls(width, height, policy, engine)


def compare_sequence(
    report,
    gpu_module,
    gpu_class,
    engine,
    candidate_path,
    candidate_hash,
    name,
    frames,
    mode,
    review_dir=None,
):
    frames = list(frames)
    height, width = frames[0].shape[:2]
    from depthsbs_app.live_policy import resolve_live

    policy = resolve_live(mode)
    previous_current = previous_candidate = None
    with ExitStack() as scope:
        current = scope.enter_context(gpu_class(width, height, policy, engine))
        candidate = scope.enter_context(
            create_candidate(
                gpu_module,
                gpu_class,
                candidate_path,
                candidate_hash,
                width,
                height,
                policy,
                engine,
            )
        )
        for index, frame in enumerate(frames):
            current_rgb, current_depth = current.render(
                frame, current.infer(frame), diagnostic=True
            )
            candidate_rgb, candidate_depth = candidate.render(
                frame, candidate.infer(frame), diagnostic=True
            )
            depth_error = np.abs(candidate_depth - current_depth)
            rgb_error = np.abs(
                candidate_rgb.astype(np.int16) - current_rgb.astype(np.int16)
            )
            current_change = (
                None
                if previous_current is None
                else temporal_change(current_rgb, previous_current)
            )
            candidate_change = (
                None
                if previous_candidate is None
                else temporal_change(candidate_rgb, previous_candidate)
            )
            row = {
                "scene": name,
                "size": [width, height],
                "mode": mode,
                "radius": policy.depth_guide_radius,
                "frame": index,
                "depth_mae": float(depth_error.mean(dtype=np.float64)),
                "depth_max": float(depth_error.max()),
                "rgb_mae": float(rgb_error.mean(dtype=np.float64)),
                "rgb_changed_fraction": float(
                    np.mean(np.any(rgb_error != 0, axis=2))
                ),
                "current_temporal_change": current_change,
                "candidate_temporal_change": candidate_change,
                "temporal_change_increase": (
                    None
                    if current_change is None
                    else candidate_change - current_change
                ),
                "temporal_change_absolute_error": (
                    None
                    if current_change is None
                    else abs(candidate_change - current_change)
                ),
            }
            row["passed"] = all(row[key] <= value for key, value in LIMITS.items())
            report["cases"].append(row)
            if not row["passed"]:
                print(json.dumps(row), flush=True)
            if review_dir is not None and index in (0, len(frames) - 1):
                stem = f"{name}-{mode}-{index}"
                for label, image in (
                    ("current", current_rgb),
                    ("candidate", candidate_rgb),
                ):
                    cv2.imwrite(
                        str(review_dir / f"{stem}-{label}.png"),
                        cv2.cvtColor(image, cv2.COLOR_RGB2BGR),
                    )
                amplified = np.clip(rgb_error * 16, 0, 255).astype(np.uint8)
                cv2.imwrite(str(review_dir / f"{stem}-diff16x.png"), amplified)
            previous_current = current_rgb.copy()
            previous_candidate = candidate_rgb.copy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--current-dll",
        type=Path,
        help="Optional hash-derived baseline DLL for chained artifact verification",
    )
    parser.add_argument("--candidate-dll", type=Path, required=True)
    parser.add_argument(
        "--candidate-source",
        type=Path,
        default=Path("experiments/cuda_projection/live_depth_guide_rolling.cu"),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--public-frames", type=int, default=6)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    if not 2 <= args.public_frames <= 30:
        raise ValueError("Public comparison must contain 2 to 30 contiguous frames")
    args.output.mkdir(parents=True)
    review_dir = args.output / "review"
    review_dir.mkdir()
    configure_resource_root(BUNDLE)

    import depthsbs_app.live_gpu_candidate as gpu_module
    from depthsbs_app.live_gpu_candidate import LiveGpuCandidate
    from depthsbs_app.trt_backend import DepthEngine
    from public_test_media import ATTRIBUTION, PublicFrames, SOURCES, prepare

    current_path = (
        args.current_dll.resolve() if args.current_dll else gpu_module.DLL_PATH.resolve()
    )
    current_hash = sha256(current_path) if args.current_dll else gpu_module.DLL_SHA256
    gpu_module.DLL_PATH = current_path
    gpu_module.DLL_SHA256 = current_hash
    candidate_path = args.candidate_dll.resolve()
    candidate_hash = sha256(candidate_path)
    report = {
        "passed": False,
        "scope": (
            "Hash-bound current DLL versus isolated guide candidate. "
            "Metrics cover aligned depth, final SBS RGB and consecutive-frame RGB "
            "change. This bounded numerical comparison and review imagery do not "
            "establish perceptual quality, VR comfort, capture cadence or 4K60."
        ),
        "acceptance": {
            **LIMITS,
            "temporal_change": (
                "Reported as a non-gating proxy because no temporal threshold was "
                "predeclared; the per-frame RGB limits remain gating."
            ),
        },
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "gpu_preflight": gpu_snapshot(),
            "current_dll": str(current_path),
            "current_dll_sha256": current_hash,
            "candidate_dll": str(candidate_path),
            "candidate_dll_sha256": candidate_hash,
            "canonical_source_sha256": sha256(
                Path("experiments/cuda_projection/live_depth.cu")
            ),
            "candidate_source": str(args.candidate_source.resolve()),
            "candidate_source_sha256": sha256(args.candidate_source),
        },
        "public_sources": prepare(),
        "public_attribution": ATTRIBUTION,
        "cases": [],
    }
    try:
        with DepthEngine() as engine:
            for width, height in ((16, 16), (127, 69), (641, 359)):
                for mode in ("performance", "balanced", "video-quality"):
                    compare_sequence(
                        report,
                        gpu_module,
                        LiveGpuCandidate,
                        engine,
                        candidate_path,
                        candidate_hash,
                        f"synthetic-motion-cut-{width}x{height}",
                        synthetic_frames(width, height),
                        mode,
                    )
            for name in SOURCES:
                for mode in ("performance", "balanced", "video-quality"):
                    compare_sequence(
                        report,
                        gpu_module,
                        LiveGpuCandidate,
                        engine,
                        candidate_path,
                        candidate_hash,
                        name,
                        PublicFrames(name, args.public_frames),
                        mode,
                        review_dir,
                    )

        summary = {
            "case_count": len(report["cases"]),
            "failed_case_count": sum(not row["passed"] for row in report["cases"]),
        }
        for key in LIMITS:
            summary[f"maximum_{key}"] = max(row[key] for row in report["cases"])
        temporal = [
            row for row in report["cases"] if row["temporal_change_increase"] is not None
        ]
        summary["maximum_temporal_change_increase"] = max(
            row["temporal_change_increase"] for row in temporal
        )
        summary["maximum_temporal_change_absolute_error"] = max(
            row["temporal_change_absolute_error"] for row in temporal
        )
        report["summary"] = summary
        report["passed"] = summary["failed_case_count"] == 0
        report["environment"]["gpu_postflight"] = gpu_snapshot()
        return 0 if report["passed"] else 1
    finally:
        (args.output / "report.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    raise SystemExit(main())
