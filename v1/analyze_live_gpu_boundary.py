"""Attribute explicit live GPU transfers and sampled stages from a benchmark run."""

import argparse
import json
import math
import statistics
from pathlib import Path


GPU_STAGES = (
    "input_h2d_normalize",
    "inference_stream_interval",
    "rgb_h2d_depth_resize",
    "sort_bounds",
    "normalize_temporal",
    "guide",
    "projection_output",
    "cpu_background",
)
HOST_STAGES = ("input_copy", "input_color", "output_color", "output_copy")


def percentile(values, fraction):
    if not values:
        raise ValueError("Cannot summarize an empty sample")
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summarize_columns(rows, names, divisor):
    if not rows or any(len(row) != len(names) for row in rows):
        raise ValueError("Invalid stage samples")
    result = {}
    for index, name in enumerate(names):
        values = [row[index] / divisor for row in rows]
        result[name] = {
            "samples": len(values),
            "p50_ms": percentile(values, 0.50),
            "p95_ms": percentile(values, 0.95),
            "p99_ms": percentile(values, 0.99),
            "mean_ms": statistics.fmean(values),
        }
    return result


def analyze(runs):
    if not isinstance(runs, list) or not runs:
        raise ValueError("Expected one or more benchmark runs")
    sizes = {row["size"] for row in runs}
    paths = {row["report"]["processing_path"] for row in runs}
    modes = {row["mode"] for row in runs}
    if len(sizes) != 1 or len(paths) != 1 or len(modes) != 1:
        raise ValueError("Runs must share size, mode and processing path")
    width, height = (int(value) for value in next(iter(sizes)).split("x"))
    final = runs[-1]["report"]
    frames = int(final["processed_frames"])
    inference_frames = int(final["inference_frames"])
    reused_frames = int(final.get("reused_depth_frames", 0))
    duration = float(final["duration_seconds"])
    if frames <= 0 or duration <= 0:
        raise ValueError("Invalid cumulative frame counters")

    h2d = int(final["explicit_cuda_h2d_bytes"])
    d2h = int(final["explicit_cuda_d2h_bytes"])
    syncs = int(final["explicit_cuda_syncs"])
    small_rgb_bytes = 518 * 518 * 3
    full_rgb_bytes = width * height * 3
    completed_fresh_frames = frames - reused_frames
    if completed_fresh_frames < 0:
        raise ValueError("Reused frames exceed processed frames")
    expected_h2d = frames * full_rgb_bytes + completed_fresh_frames * small_rgb_bytes
    minimum_d2h = frames * 4
    minimum_syncs = frames * 2 if next(iter(paths)) == "gpu-texture" else None

    gpu_rows = [sample for row in runs for sample in row["gpu_stage_samples_ns"]]
    host_rows = [sample for row in runs for sample in row["host_bridge_samples_ns"]]
    gpu = summarize_columns(gpu_rows, GPU_STAGES, 1e6)
    host = summarize_columns(host_rows, HOST_STAGES, 1e6)
    ranked = sorted(
        (
            {"stage": name, "p50_ms": values["p50_ms"]}
            for name, values in {**gpu, **host}.items()
            if name not in ("inference_stream_interval", "cpu_background")
        ),
        key=lambda row: row["p50_ms"],
        reverse=True,
    )
    return {
        "scope": (
            "Explicit CUDA submissions and sampled stream intervals from the supplied "
            "live benchmark. Stream intervals can include enqueue gaps and are not GPU "
            "utilization or an additive wall-clock critical path."
        ),
        "workload": {
            "size": next(iter(sizes)),
            "mode": next(iter(modes)),
            "processing_path": next(iter(paths)),
            "windows": len(runs),
            "cumulative_duration_seconds": duration,
            "processed_frames": frames,
            "reported_inference_frames": inference_frames,
            "completed_fresh_frames": completed_fresh_frames,
            "reused_depth_frames": reused_frames,
            "counter_skew_inference_minus_processed": inference_frames - frames,
        },
        "explicit_transfers": {
            "h2d_bytes": h2d,
            "d2h_bytes": d2h,
            "syncs": syncs,
            "h2d_bytes_per_processed_frame": h2d / frames,
            "d2h_bytes_per_processed_frame": d2h / frames,
            "syncs_per_processed_frame": syncs / frames,
            "h2d_gb_per_second": h2d / duration / 1e9,
            "d2h_bytes_per_second": d2h / duration,
            "expected_per_frame": {
                "small_rgb_h2d_bytes": small_rgb_bytes,
                "full_rgb_h2d_bytes": full_rgb_bytes,
                "invalid_flag_d2h_bytes": 4,
                "native_syncs": 2,
            },
            "formula_checks": {
                "h2d_expected_for_completed_fresh_frames": h2d == expected_h2d,
                "d2h_minimum_only": d2h == minimum_d2h,
                "syncs_minimum_only": minimum_syncs is None or syncs == minimum_syncs,
            },
        },
        "gpu_stage_summary": gpu,
        "host_stage_summary": host,
        "ranked_sampled_p50": ranked,
        "interpretation": {
            "largest_sampled_stage": ranked[0]["stage"],
            "host_capture_input_is_zero_copy": False,
            "native_output_avoids_full_sbs_d2h": d2h == minimum_d2h,
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    result = analyze(json.loads(args.runs.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
