"""oVDA temporal-alignment experiment using NVIDIA Optical Flow hardware."""

import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import statistics
import time

import cv2
import numpy as np

from nvof_probe import NvofProbe, checked_manifest, expand_flow
from public_test_media import PublicFrames
from test_ovda_device_post import create_engine, engine_classes

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path("C:/TensorRT/TensorRT-11.2.1.2/bin")
CLIPS = ("OfficeWalk", "FloorballGame", "ParkingGarage")
PAIR_INDICES = (1, 5, 10, 20, 30, 40, 50, 59)


def normalize(depth):
    value = np.asarray(depth, dtype=np.float32).squeeze()
    if value.ndim != 2 or not np.isfinite(value).all():
        raise ValueError("Invalid oVDA depth")
    low, high = np.percentile(value, [5, 95])
    return np.clip((value - low) / max(high - low, 1e-6), 0, 1).astype(np.float32)


def warp(value, flow):
    height, width = flow.shape[:2]
    y, x = np.mgrid[:height, :width].astype(np.float32)
    return cv2.remap(
        value.astype(np.float32),
        x + flow[:, :, 0],
        y + flow[:, :, 1],
        cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
    )


def aligned_metrics(old_rgb, rgb, old_depth, depth, backward, forward):
    height, width = rgb.shape[:2]
    for flow in (backward, forward):
        if flow.shape != (height, width, 2) or not np.isfinite(flow).all():
            raise ValueError("Invalid expanded NVOF field")
    y, x = np.mgrid[:height, :width].astype(np.float32)
    mapped_x = x + backward[:, :, 0]
    mapped_y = y + backward[:, :, 1]
    warped_old_rgb = warp(old_rgb, backward)
    warped_forward = warp(forward, backward)
    valid = (
        (mapped_x >= 1)
        & (mapped_x < width - 2)
        & (mapped_y >= 1)
        & (mapped_y < height - 2)
    )
    valid &= np.linalg.norm(backward + warped_forward, axis=2) <= 2.0
    photo = np.max(np.abs(rgb.astype(np.float32) - warped_old_rgb), axis=2)
    valid &= photo <= 24
    valid = cv2.erode(valid.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    edges = cv2.dilate(cv2.Canny(gray, 60, 120), np.ones((5, 5), np.uint8)).astype(bool)
    warped_depth = warp(old_depth, backward)
    warped_delta = np.abs(depth - warped_depth)
    fixed_delta = np.abs(depth - old_depth)

    def mean(value, mask):
        return float(value[mask].mean()) if mask.any() else None

    return {
        "valid_fraction": float(valid.mean()),
        "edge_valid_fraction": float((valid & edges).mean()),
        "warped_depth_mae": mean(warped_delta, valid),
        "fixed_depth_mae": mean(fixed_delta, valid),
        "warped_edge_depth_mae": mean(warped_delta, valid & edges),
        "fixed_edge_depth_mae": mean(fixed_delta, valid & edges),
        "warped_rgb_mae": mean(
            np.mean(np.abs(rgb.astype(np.float32) - warped_old_rgb), axis=2), valid
        ),
        "fixed_rgb_mae": mean(
            np.mean(np.abs(rgb.astype(np.float32) - old_rgb), axis=2), valid
        ),
        "median_motion_pixels": float(
            np.median(np.linalg.norm(backward[valid], axis=1))
        )
        if valid.any()
        else None,
    }


def analytic_direction():
    height, width, shift = 360, 640, 8
    rng = np.random.default_rng(2906)
    old = cv2.GaussianBlur(
        rng.integers(0, 256, (height, width, 3), np.uint8), (0, 0), 1.2
    )
    current = np.empty_like(old)
    current[:, :shift] = old[:, :1]
    current[:, shift:] = old[:, :-shift]
    with NvofProbe(width, height) as probe:
        _, first = probe.prepare(np.ascontiguousarray(old), reset=True)
        raw, timing = probe.prepare(np.ascontiguousarray(current))
    flow = expand_flow(raw, width, height)
    interior = flow[16:-16, shift + 16 : -16]
    median = np.median(interior.reshape(-1, 2), axis=0)
    warped = warp(old, flow)
    mask = np.zeros((height, width), bool)
    mask[16:-16, shift + 16 : -16] = True
    warped_mae = float(
        np.abs(warped.astype(np.float32) - current).mean(axis=2)[mask].mean()
    )
    fixed_mae = float(
        np.abs(old.astype(np.float32) - current).mean(axis=2)[mask].mean()
    )
    passed = (
        not first["has_flow"]
        and timing["has_flow"]
        and abs(float(median[0]) + shift) <= 1.5
        and abs(float(median[1])) <= 1.5
        and warped_mae < fixed_mae * 0.5
    )
    return {
        "passed": bool(passed),
        "expected_current_to_previous_dx": -shift,
        "median_dx": float(median[0]),
        "median_dy": float(median[1]),
        "warped_rgb_mae": warped_mae,
        "fixed_rgb_mae": fixed_mae,
        "timing": timing,
    }


def load_clip(name):
    return [np.ascontiguousarray(frame) for frame in PublicFrames(name, 60)]


def infer_depths(frames, HostEngine):
    engine = create_engine(HostEngine)
    values = []
    try:
        engine.reset("start")
        for frame in frames:
            values.append(normalize(engine.infer(frame)))
        telemetry = engine.telemetry()
    finally:
        engine.close()
    return values, telemetry


def backward_sequence(frames):
    raw_fields = []
    timings = []
    python_us = []
    with NvofProbe(frames[0].shape[1], frames[0].shape[0]) as probe:
        for index, frame in enumerate(frames):
            started = time.perf_counter_ns()
            raw, timing = probe.prepare(frame, reset=index == 0)
            python_us.append((time.perf_counter_ns() - started) / 1000)
            raw_fields.append(raw)
            timings.append(timing)
    return raw_fields, timings, python_us


def forward_for_pair(current, old):
    height, width = current.shape[:2]
    with NvofProbe(width, height) as probe:
        probe.prepare(current, reset=True)
        raw, timing = probe.prepare(old)
    if not timing["has_flow"]:
        raise RuntimeError("Forward NVOF pair did not produce flow")
    return expand_flow(raw, width, height)


def summarize_clip(rows, timings, python_us):
    def average(key):
        values = [row[key] for row in rows if row[key] is not None]
        return float(np.mean(values)) if values else None

    warped = average("warped_depth_mae")
    fixed = average("fixed_depth_mae")
    warped_edge = average("warped_edge_depth_mae")
    fixed_edge = average("fixed_edge_depth_mae")
    measured_timing = [value for value in timings if value["has_flow"]]
    return {
        "pairs": len(rows),
        "valid_fraction": average("valid_fraction"),
        "edge_valid_fraction": average("edge_valid_fraction"),
        "warped_depth_mae": warped,
        "fixed_depth_mae": fixed,
        "depth_mae_ratio": warped / fixed if fixed else None,
        "warped_edge_depth_mae": warped_edge,
        "fixed_edge_depth_mae": fixed_edge,
        "edge_depth_mae_ratio": warped_edge / fixed_edge if fixed_edge else None,
        "warped_rgb_mae": average("warped_rgb_mae"),
        "fixed_rgb_mae": average("fixed_rgb_mae"),
        "median_motion_pixels": average("median_motion_pixels"),
        "timing_median_us": {
            key: statistics.median(value[key] for value in measured_timing)
            for key in ("pack_us", "upload_us", "nvof_us")
        },
        "python_call_median_us": statistics.median(python_us[1:]),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Fresh output required")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "passed": False,
        "candidate_accepted": False,
        "manifest": checked_manifest(),
        "analytic": {},
        "clips": {},
        "scope": (
            "Host-RGB CUDA NVOF with coarse-flow readback and CPU warp; oVDA c16 "
            "FP32 depth. Alignment proxy only, without ground-truth depth, renderer "
            "integration, inference skipping, live latency or VR acceptance."
        ),
    }

    def save():
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    save()
    report["analytic"] = analytic_direction()
    save()
    if not report["analytic"]["passed"]:
        raise AssertionError("NVOF current-to-previous direction gate failed")
    HostEngine, _, _ = engine_classes()
    with ExitStack() as stack:
        stack.enter_context(os.add_dll_directory(str(RUNTIME)))
        for name in CLIPS:
            frames = load_clip(name)
            depths, telemetry = infer_depths(frames, HostEngine)
            backward_raw, timings, python_us = backward_sequence(frames)
            rows = []
            for index in PAIR_INDICES:
                backward = expand_flow(
                    backward_raw[index], frames[index].shape[1], frames[index].shape[0]
                )
                forward = forward_for_pair(frames[index], frames[index - 1])
                started = time.perf_counter_ns()
                row = aligned_metrics(
                    frames[index - 1],
                    frames[index],
                    depths[index - 1],
                    depths[index],
                    backward,
                    forward,
                )
                row["cpu_metric_us"] = (time.perf_counter_ns() - started) / 1000
                row["frame"] = index
                rows.append(row)
            summary = summarize_clip(rows, timings, python_us)
            report["clips"][name] = {
                "input_sha256": hashlib.sha256(
                    PublicFrames(name, 60).path.read_bytes()
                ).hexdigest(),
                "model": telemetry,
                "rows": rows,
                "summary": summary,
            }
            save()
            print(json.dumps({name: summary}, indent=2), flush=True)
    summaries = [value["summary"] for value in report["clips"].values()]
    report["candidate_accepted"] = all(
        summary["valid_fraction"] >= 0.2
        and summary["depth_mae_ratio"] <= 1.0
        and summary["edge_depth_mae_ratio"] <= 1.0
        for summary in summaries
    )
    report["passed"] = True
    save()
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "candidate_accepted": report["candidate_accepted"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
