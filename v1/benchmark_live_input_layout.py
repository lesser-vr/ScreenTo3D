"""CPU microbenchmark for rejected full-resolution BGRA handoff alternatives."""

import argparse
import json
import statistics
import time
from pathlib import Path

import cv2
import numpy as np


def measure(operation, iterations):
    for _ in range(5):
        operation()
    samples = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        operation()
        samples.append((time.perf_counter_ns() - started) / 1e6)
    ordered = sorted(samples)
    return {
        "iterations": iterations,
        "median_ms": statistics.median(samples),
        "p95_ms": ordered[min(len(ordered) - 1, math_index(len(ordered), 0.95))],
        "samples_ms": samples,
    }


def math_index(count, fraction):
    return max(0, int((count - 1) * fraction + 0.999999999))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--size", default="3840x2160")
    parser.add_argument("--iterations", type=int, default=30)
    args = parser.parse_args()
    if args.iterations < 5:
        raise ValueError("At least five iterations are required")
    if args.output.exists():
        raise FileExistsError(args.output)
    width, height = (int(value) for value in args.size.split("x"))
    if width < 16 or height < 16:
        raise ValueError("Invalid dimensions")
    source = np.random.default_rng(1).integers(
        0, 256, (height, width, 4), dtype=np.uint8
    )

    def current_rgb():
        rgb = cv2.cvtColor(source, cv2.COLOR_BGRA2RGB)
        return cv2.resize(rgb, (518, 518), interpolation=cv2.INTER_CUBIC)

    def owned_bgra():
        bgra = source.copy()
        small = cv2.resize(bgra, (518, 518), interpolation=cv2.INTER_CUBIC)
        return cv2.cvtColor(small, cv2.COLOR_BGRA2RGB)

    current = current_rgb()
    candidate = owned_bgra()
    result = {
        "scope": (
            "Host ownership/color/resize microbenchmark only; excludes CUDA kernel "
            "conversion and is not an end-to-end live throughput result."
        ),
        "size": args.size,
        "small_size": "518x518",
        "exact_small_rgb": bool(np.array_equal(current, candidate)),
        "current_full_bgra_to_rgb_then_resize": measure(current_rgb, args.iterations),
        "candidate_owned_bgra_then_resize_and_small_rgb": measure(
            owned_bgra, args.iterations
        ),
        "cuda_h2d_bytes_per_frame": {
            "current": width * height * 3 + 518 * 518 * 3,
            "candidate": width * height * 4 + 518 * 518 * 3,
            "candidate_increase": width * height,
        },
    }
    current_ms = result["current_full_bgra_to_rgb_then_resize"]["median_ms"]
    candidate_ms = result["candidate_owned_bgra_then_resize_and_small_rgb"]["median_ms"]
    result["median_delta_ms"] = candidate_ms - current_ms
    result["promotion_supported"] = bool(
        result["exact_small_rgb"]
        and candidate_ms < current_ms
        and result["cuda_h2d_bytes_per_frame"]["candidate_increase"] <= 0
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
