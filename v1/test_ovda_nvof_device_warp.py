"""Validate CUDA-resident NVOF depth warp and the existing SBS consumer."""

import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import statistics
import threading
import time

import cv2
import numpy as np
import torch

from nvof_device_warp import NvofDeviceWarp, bilinear_depth_warp, checked_manifest
from nvof_probe import expand_flow
from public_test_media import PublicFrames
from test_ovda_device_post import SourcePost, create_engine, engine_classes
from test_ovda_nvof import CLIPS, PAIR_INDICES, normalize

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path("C:/TensorRT/TensorRT-11.2.1.2/bin")
POST_DLL = ROOT / "out/ovda-device-post-spike/live_depth.dll"


class TensorDepthToken:
    def __init__(self, tensor):
        self.tensor = tensor
        self.pointer = int(tensor.data_ptr())
        self.stream = int(torch.cuda.current_stream().cuda_stream)
        self.shape = tuple(tensor.shape)

    def validate(self):
        if (
            self.tensor.device.type != "cuda"
            or self.tensor.dtype != torch.float32
            or not self.tensor.is_contiguous()
            or not self.pointer
        ):
            raise ValueError("Invalid analytic CUDA depth")


def translated_pair(height=360, width=640, shift=8):
    rng = np.random.default_rng(907)
    old = cv2.GaussianBlur(
        rng.integers(0, 256, (height, width, 3), np.uint8), (0, 0), 1.2
    )
    current = np.empty_like(old)
    current[:, :shift] = old[:, :1]
    current[:, shift:] = old[:, :-shift]
    depth = np.ascontiguousarray(
        (
            np.linspace(0, 1, width, dtype=np.float32)[None, :]
            + np.linspace(0, 0.25, height, dtype=np.float32)[:, None]
        ).astype(np.float32)
    )
    return np.ascontiguousarray(old), np.ascontiguousarray(current), depth, shift


def compare_warp(previous, raw, actual, actual_valid, width, height):
    flow = expand_flow(raw, width, height)
    expected, expected_valid = bilinear_depth_warp(previous, flow)
    valid_exact = np.array_equal(actual_valid, expected_valid)
    delta = np.abs(actual - expected)
    return {
        "valid_exact": bool(valid_exact),
        "valid_pixels": int(expected_valid.sum()),
        "max_abs_error_all": float(delta.max()),
        "max_abs_error_valid": float(delta[expected_valid != 0].max()),
        "flow": flow,
    }


def analytic_gate():
    old, current, previous, shift = translated_pair()
    device = torch.from_numpy(previous[None]).cuda().contiguous()
    token = TensorDepthToken(device)
    with NvofDeviceWarp(old.shape[1], old.shape[0]) as warp:
        seeded, seed_timing = warp.seed(old, token, diagnostic=True)
        foreign_thread_errors = []

        def use_from_foreign_thread():
            try:
                warp.warp(current)
            except Exception as error:
                foreign_thread_errors.append(str(error))

        thread = threading.Thread(target=use_from_foreign_thread)
        thread.start()
        thread.join()
        foreign_thread_rejected = bool(
            foreign_thread_errors and "another thread" in foreign_thread_errors[0]
        )
        actual_token, raw, actual, valid, timing = warp.warp(current, diagnostic=True)
        comparison = compare_warp(
            previous, raw, actual, valid, old.shape[1], old.shape[0]
        )
        flow = comparison.pop("flow")
        median = np.median(flow[24:-24, shift + 24 : -24].reshape(-1, 2), axis=0)
        early_reuse_rejected = False
        try:
            warp.warp(current)
        except RuntimeError:
            early_reuse_rejected = True
        warp.complete(actual_token, retain=True)
        expired_after_complete = False
        try:
            actual_token.validate()
        except RuntimeError:
            expired_after_complete = True
        chained_token, chained_raw, chained_depth, chained_valid, chained_timing = (
            warp.warp(current, diagnostic=False)
        )
        no_diagnostic_passed = (
            chained_raw is None
            and chained_depth is None
            and chained_valid is None
            and chained_timing["readback_us"] == 0
            and chained_token.pointer != 0
        )
        warp.complete(chained_token, retain=False)
        passed = (
            np.array_equal(seeded, previous)
            and comparison["valid_exact"]
            and comparison["max_abs_error_all"] <= 1e-6
            and abs(float(median[0]) + shift) <= 1.5
            and abs(float(median[1])) <= 1.5
            and early_reuse_rejected
            and expired_after_complete
            and no_diagnostic_passed
            and foreign_thread_rejected
        )
        return {
            "passed": bool(passed),
            "seed_exact": bool(np.array_equal(seeded, previous)),
            "median_dx": float(median[0]),
            "median_dy": float(median[1]),
            "early_reuse_rejected": early_reuse_rejected,
            "expired_after_complete": expired_after_complete,
            "no_diagnostic_chain_passed": no_diagnostic_passed,
            "no_diagnostic_chain_timing": chained_timing,
            "foreign_thread_rejected": foreign_thread_rejected,
            "seed_timing": seed_timing,
            "warp_timing": timing,
            **comparison,
        }


def pending_close_gate():
    old, current, previous, _ = translated_pair()
    token = TensorDepthToken(torch.from_numpy(previous[None]).cuda().contiguous())
    warp = NvofDeviceWarp(old.shape[1], old.shape[0])
    warp.seed(old, token)
    pending, _, _, _, _ = warp.warp(current)
    warp.close()
    closed_token_rejected = False
    try:
        pending.validate()
    except RuntimeError:
        closed_token_rejected = True
    warp.close()
    return {
        "passed": bool(closed_token_rejected and warp.handle is None),
        "pending_token_rejected_after_close": closed_token_rejected,
        "idempotent_close": warp.handle is None,
    }


def load_clip(name):
    source = PublicFrames(name, 60)
    return source, [np.ascontiguousarray(frame) for frame in source]


def public_clip(name, DeviceEngine, policy):
    source, frames = load_clip(name)
    height, width = frames[0].shape[:2]
    engine = create_engine(DeviceEngine)
    rows = []
    seed_indices = {index - 1 for index in PAIR_INDICES}
    previous = None
    try:
        engine.reset("start")
        with NvofDeviceWarp(width, height) as warp:
            # Construct the post contexts only after the NVOF-owned stream exists.
            with (
                SourcePost(
                    engine,
                    width,
                    height,
                    policy,
                    dll_path=POST_DLL,
                    stream=warp.stream,
                ) as device_post,
                SourcePost(
                    engine,
                    width,
                    height,
                    policy,
                    dll_path=POST_DLL,
                    stream=warp.stream,
                ) as host_post,
            ):
                for index, frame in enumerate(frames):
                    depth_token = engine.infer_device(frame)
                    try:
                        if index in seed_indices:
                            previous, seed_timing = warp.seed(
                                frame, depth_token, diagnostic=True
                            )
                        elif index in PAIR_INDICES:
                            current_depth = np.ascontiguousarray(
                                depth_token.tensor.detach().cpu().numpy()[0]
                            )
                    finally:
                        engine.complete_device(depth_token)

                    if index not in PAIR_INDICES:
                        continue
                    if previous is None:
                        raise RuntimeError("Missing device-warp seed")
                    began = time.perf_counter_ns()
                    warp_token, raw, actual, valid, timing = warp.warp(
                        frame, diagnostic=True
                    )
                    wrapper_us = (time.perf_counter_ns() - began) / 1000
                    comparison = compare_warp(
                        previous, raw, actual, valid, width, height
                    )
                    flow = comparison.pop("flow")
                    began = time.perf_counter_ns()
                    device_sbs = device_post.render_pointer(
                        frame,
                        warp_token.pointer,
                        producer_stream=warp_token.stream,
                        reset=True,
                    )
                    device_post_us = (time.perf_counter_ns() - began) / 1000
                    host_sbs = host_post.render(
                        frame, actual[None], device=False, reset=True
                    )
                    sbs_exact = all(
                        np.array_equal(left, right)
                        for left, right in zip(device_sbs, host_sbs)
                    )
                    sbs_max = max(
                        int(np.max(np.abs(left.astype(np.int16) - right)))
                        for left, right in zip(device_sbs, host_sbs)
                    )
                    warp.complete(warp_token, retain=False)
                    normalized_previous = normalize(previous)
                    normalized_actual, _ = bilinear_depth_warp(
                        normalized_previous, flow
                    )
                    normalized_current = normalize(current_depth)
                    mask = valid != 0
                    warped_mae = float(
                        np.abs(normalized_current - normalized_actual)[mask].mean()
                    )
                    fixed_mae = float(
                        np.abs(normalized_current - normalized_previous)[mask].mean()
                    )
                    rows.append(
                        {
                            "frame": index,
                            "seed_timing": seed_timing,
                            "timing": timing,
                            "wrapper_us": wrapper_us,
                            "device_post_sbs_us": device_post_us,
                            "sbs_exact": bool(sbs_exact),
                            "sbs_max_channel_error": sbs_max,
                            "warped_depth_mae": warped_mae,
                            "fixed_depth_mae": fixed_mae,
                            "inbounds_only_depth_mae_ratio": warped_mae / fixed_mae
                            if fixed_mae
                            else None,
                            "median_motion_pixels": float(
                                np.median(np.linalg.norm(flow[mask], axis=1))
                            ),
                            **comparison,
                        }
                    )
                    previous = None
        telemetry = engine.telemetry()
    finally:
        engine.close()

    def median(path):
        values = []
        for row in rows:
            value = row
            for key in path:
                value = value[key]
            values.append(value)
        return statistics.median(values)

    summary = {
        "pairs": len(rows),
        "all_valid_exact": all(row["valid_exact"] for row in rows),
        "maximum_warp_abs_error": max(row["max_abs_error_all"] for row in rows),
        "exact_sbs_pairs": sum(row["sbs_exact"] for row in rows),
        "maximum_sbs_channel_error": max(row["sbs_max_channel_error"] for row in rows),
        "median_inbounds_only_depth_mae_ratio": median(
            ("inbounds_only_depth_mae_ratio",)
        ),
        "median_valid_fraction": median(("valid_pixels",)) / (width * height),
        "timing_median_us": {
            key: median(("timing", key))
            for key in ("pack_us", "upload_us", "nvof_us", "warp_us", "readback_us")
        },
        "wrapper_median_us": median(("wrapper_us",)),
        "device_post_sbs_median_us": median(("device_post_sbs_us",)),
    }
    summary["runtime_stage_median_us_excluding_readback"] = sum(
        summary["timing_median_us"][key]
        for key in ("pack_us", "upload_us", "nvof_us", "warp_us")
    )
    summary["diagnostic_bytes_excluded_per_pair"] = (
        ((width + 1) // 2) * ((height + 1) // 2) * 4
        + width * height * 4
        + width * height
    )
    passed = (
        len(rows) == len(PAIR_INDICES)
        and summary["all_valid_exact"]
        and summary["maximum_warp_abs_error"] <= 1e-5
        and summary["exact_sbs_pairs"] == len(rows)
        and summary["maximum_sbs_channel_error"] == 0
        and telemetry["pending_device_depth"] is False
    )
    return {
        "passed": bool(passed),
        "input": str(source.path.resolve()),
        "input_sha256": hashlib.sha256(source.path.read_bytes()).hexdigest(),
        "rows": rows,
        "summary": summary,
        "engine": telemetry,
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
        "scope": (
            "Isolated host-RGB -> CUDA NVOF -> CUDA float32 depth warp -> existing "
            "CUDA post/SBS consumer. Diagnostic flow/depth/validity readbacks are "
            "oracle-only. No live scheduling, inference skipping, native capture, "
            "shared-texture presentation, idle-GPU benchmark, or VR claim."
        ),
        "analytic": {},
        "pending_close": {},
        "clips": {},
        "warp_manifest": checked_manifest(),
    }

    post_manifest = json.loads(
        (POST_DLL.parent / "build-manifest.json").read_text(encoding="utf-8-sig")
    )
    post_hash = hashlib.sha256(POST_DLL.read_bytes()).hexdigest()
    if post_hash.lower() != post_manifest.get("dll_sha256", "").lower():
        raise ValueError("CUDA post/SBS DLL checksum mismatch")
    report["post_sbs_dll_sha256"] = post_hash

    def save():
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    save()
    report["analytic"] = analytic_gate()
    report["pending_close"] = pending_close_gate()
    save()
    if not report["analytic"]["passed"] or not report["pending_close"]["passed"]:
        raise AssertionError("Analytic NVOF device-depth warp failed")
    _, DeviceEngine, _ = engine_classes()
    from depthsbs_app.live_policy import resolve_live

    policy = resolve_live("video-quality")
    with ExitStack() as stack:
        stack.enter_context(os.add_dll_directory(str(RUNTIME)))
        for name in CLIPS:
            result = public_clip(name, DeviceEngine, policy)
            report["clips"][name] = result
            save()
            print(json.dumps({name: result["summary"]}, indent=2), flush=True)
            if not result["passed"]:
                raise AssertionError(f"NVOF device-depth warp failed for {name}")
    report["candidate_accepted"] = True
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
