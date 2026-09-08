"""Exact and timed VDA host/device/shared-texture boundary comparison."""

import argparse
from contextlib import ExitStack
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import statistics
import sys
import time

import numpy as np

from test_ovda_device_post import (
    SourcePost,
    load_frames,
    reset_engine,
    reset_flags,
)
from test_ovda_device_texture import TexturePost

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path("C:/TensorRT/TensorRT-11.2.1.2/bin")
ARTIFACT = ROOT / "out/vda-local/518x924-fp32"
TEXTURE_DLL = ROOT / "out/vda-device-texture-spike/vda_device_texture_spike.dll"


def device_engine_class():
    name = "_depthsbs_vda_device_depth"
    if name not in sys.modules:
        path = ROOT / "experiments/vda/device_depth.py"
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name].VdaDeviceEngine


def create_engine(Engine):
    return Engine(ARTIFACT, RUNTIME)


def host_references(HostEngine, source, flags, policy):
    engine = create_engine(HostEngine)
    depths, outputs = [], []
    try:
        engine.reset("start")
        with SourcePost(
            engine,
            source[0].shape[1],
            source[0].shape[0],
            policy,
            TEXTURE_DLL,
        ) as post:
            for index, (frame, reset) in enumerate(zip(source[:12], flags[:12])):
                reset_engine(engine, reset, index)
                depth = engine.infer(frame)
                depths.append(depth.copy())
                outputs.append(
                    np.concatenate(
                        post.render(frame, depth, device=False, reset=reset), axis=1
                    )
                )
    finally:
        engine.close()
    return depths, outputs


def device_host_parity(DeviceEngine, source, flags, policy, depths, outputs):
    engine = create_engine(DeviceEngine)
    depth_exact = sbs_exact = rejected = expired = 0
    depth_error = 0.0
    channel_error = 0
    try:
        engine.reset("start")
        with SourcePost(
            engine,
            source[0].shape[1],
            source[0].shape[0],
            policy,
            TEXTURE_DLL,
        ) as post:
            for index, (frame, reset) in enumerate(zip(source[:12], flags[:12])):
                reset_engine(engine, reset, index)
                token = engine.infer_device(frame)
                try:
                    try:
                        engine.infer_device(frame)
                    except RuntimeError:
                        rejected += 1
                    else:
                        raise AssertionError("Pending VDA token was reused")
                    engine.stream.synchronize()
                    actual_depth = token.tensor.cpu().numpy().copy()
                    depth_exact += int(np.array_equal(actual_depth, depths[index]))
                    depth_error = max(
                        depth_error,
                        float(np.max(np.abs(actual_depth - depths[index]))),
                    )
                    actual = np.concatenate(
                        post.render(frame, token, device=True, reset=reset), axis=1
                    )
                    frame_exact = np.array_equal(actual, outputs[index])
                    sbs_exact += int(frame_exact)
                    channel_error = max(
                        channel_error,
                        int(np.max(np.abs(actual.astype(np.int16) - outputs[index]))),
                    )
                    if not frame_exact:
                        raise AssertionError(f"VDA SBS mismatch at frame {index}")
                finally:
                    engine.complete_device(token)
                try:
                    token.validate()
                except RuntimeError:
                    expired += 1
                else:
                    raise AssertionError("Completed VDA token remained valid")
    finally:
        engine.close()
    return {
        "frames": 12,
        "exact_depth_frames": depth_exact,
        "maximum_depth_absolute_error": depth_error,
        "exact_host_sbs_frames": sbs_exact,
        "maximum_host_sbs_channel_error": channel_error,
        "rejected_early_reuse": rejected,
        "expired_after_complete": expired,
    }


def texture_parity(DeviceEngine, source, flags, policy, outputs):
    engine = create_engine(DeviceEngine)
    exact = alpha = 0
    maximum = 0
    try:
        engine.reset("start")
        with TexturePost(
            engine,
            source[0].shape[1],
            source[0].shape[0],
            policy,
            True,
            TEXTURE_DLL,
        ) as post:
            for index, (frame, reset) in enumerate(zip(source[:12], flags[:12])):
                reset_engine(engine, reset, index)
                token = engine.infer_device(frame)
                try:
                    actual = post.render_texture(
                        frame, token, reset=reset, diagnostic=True
                    )
                finally:
                    engine.complete_device(token)
                rgb = actual[:, :, :3]
                frame_exact = np.array_equal(rgb, outputs[index])
                exact += int(frame_exact)
                alpha += int(np.all(actual[:, :, 3] == 255))
                maximum = max(
                    maximum,
                    int(np.max(np.abs(rgb.astype(np.int16) - outputs[index]))),
                )
                if not frame_exact:
                    raise AssertionError(f"VDA texture mismatch at frame {index}")
    finally:
        engine.close()
    return {
        "frames": 12,
        "exact_sbs_frames": exact,
        "opaque_alpha_frames": alpha,
        "maximum_channel_error": maximum,
    }


def run_path(Engine, source, flags, policy, path):
    engine = create_engine(Engine)
    samples = []
    try:
        engine.reset("start")
        if path == "device-depth-shared-texture":
            post = TexturePost(
                engine,
                source[0].shape[1],
                source[0].shape[0],
                policy,
                False,
                TEXTURE_DLL,
            )
        else:
            post = SourcePost(
                engine,
                source[0].shape[1],
                source[0].shape[0],
                policy,
                TEXTURE_DLL,
            )
        with post:
            began = time.perf_counter()
            for index, (frame, reset) in enumerate(zip(source, flags)):
                reset_engine(engine, reset, index)
                started = time.perf_counter()
                if path == "host-depth-host-sbs":
                    post.render(frame, engine.infer(frame), device=False, reset=reset)
                else:
                    token = engine.infer_device(frame)
                    try:
                        if path == "device-depth-host-sbs":
                            post.render(frame, token, device=True, reset=reset)
                        else:
                            post.render_texture(frame, token, reset=reset)
                    finally:
                        engine.complete_device(token)
                samples.append((time.perf_counter() - started) * 1000)
            wall = time.perf_counter() - began
        telemetry = engine.telemetry()
    finally:
        engine.close()
    return wall, samples, telemetry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.output.exists() or args.repeats <= 0:
        raise ValueError("Fresh output and positive repeats required")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    source = load_frames(args.input)
    height, width = source[0].shape[:2]
    from depthsbs_app.live_policy import resolve_live
    from depthsbs_app.vda_backend import VdaEngine

    policy = resolve_live("video-quality")
    flags = reset_flags(source, policy.scene_cut_threshold)
    DeviceEngine = device_engine_class()
    manifest = json.loads(
        (TEXTURE_DLL.parent / "build-manifest.json").read_text(encoding="utf-8-sig")
    )
    dll_hash = hashlib.sha256(TEXTURE_DLL.read_bytes()).hexdigest()
    if dll_hash.lower() != manifest["dll_sha256"].lower():
        raise ValueError("VDA texture DLL checksum mismatch")
    report = {
        "passed": False,
        "input": str(args.input.resolve()),
        "input_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "artifact": str(ARTIFACT.resolve()),
        "texture_dll": str(TEXTURE_DLL.resolve()),
        "texture_dll_sha256": dll_hash,
        "mode": policy.name,
        "frames_per_run": len(source),
        "scene_reset_indices": [index for index, reset in enumerate(flags) if reset],
        "parity": {},
        "rows": [],
        "scope": (
            "Decoded host RGB through explicit VDA Small TensorRT FP32. The device "
            "path removes resized-depth D2H/re-upload; shared texture also removes "
            "host SBS readback. Preprocessing, RGB upload, per-frame synchronization, "
            "VDA cache assembly and a CPU consumer command remain; zero_copy=false."
        ),
    }

    def save():
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    save()
    with ExitStack() as stack:
        stack.enter_context(os.add_dll_directory(str(RUNTIME)))
        depths, outputs = host_references(VdaEngine, source, flags, policy)
        report["parity"]["device_host"] = device_host_parity(
            DeviceEngine, source, flags, policy, depths, outputs
        )
        report["parity"]["shared_texture"] = texture_parity(
            DeviceEngine, source, flags, policy, outputs
        )
        save()
        print(json.dumps(report["parity"], indent=2), flush=True)

        paths = (
            ("host-depth-host-sbs", VdaEngine),
            ("device-depth-host-sbs", DeviceEngine),
            ("device-depth-shared-texture", DeviceEngine),
        )
        for round_index in range(args.repeats + 1):
            rotation = round_index % len(paths)
            ordered = paths[rotation:] + paths[:rotation]
            for execution_index, (path, Engine) in enumerate(ordered):
                wall, samples, telemetry = run_path(Engine, source, flags, policy, path)
                row = {
                    "round": round_index,
                    "execution_index": execution_index,
                    "warmup": round_index == 0,
                    "path": path,
                    "fps": len(source) / wall,
                    "elapsed_seconds": wall,
                    "mean_ms": statistics.mean(samples),
                    "p95_ms": float(np.percentile(samples, 95)),
                    "telemetry": telemetry,
                }
                report["rows"].append(row)
                save()
                print(
                    json.dumps(
                        {
                            key: row[key]
                            for key in ("round", "warmup", "path", "fps", "p95_ms")
                        }
                    ),
                    flush=True,
                )
        names = tuple(path for path, _ in paths)
        report["summary"] = {
            name: {
                "median_fps": statistics.median(
                    row["fps"]
                    for row in report["rows"]
                    if row["path"] == name and not row["warmup"]
                ),
                "runs": args.repeats,
            }
            for name in names
        }
        host_fps = report["summary"][names[0]]["median_fps"]
        device_fps = report["summary"][names[1]]["median_fps"]
        texture_fps = report["summary"][names[2]]["median_fps"]
        report["summary"].update(
            device_change_percent=(device_fps / host_fps - 1) * 100,
            texture_change_from_device_percent=(texture_fps / device_fps - 1) * 100,
            combined_change_percent=(texture_fps / host_fps - 1) * 100,
        )
        report["transfer_accounting_per_60_frames"] = {
            "depth_d2h_bytes_avoided": width * height * 4 * 60,
            "host_sbs_d2h_bytes_avoided": width * height * 3 * 2 * 60,
        }
        report["passed"] = True
        save()
        print(json.dumps(report["summary"], indent=2), flush=True)


if __name__ == "__main__":
    main()
