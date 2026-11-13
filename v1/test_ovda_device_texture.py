"""Exact and timed oVDA device-depth to shared-D3D11-texture spike."""

import argparse
import ctypes as ct
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import statistics
import time

import numpy as np

from test_ovda_device_post import (
    DLL as HOST_OUTPUT_DLL,
    SourcePost,
    create_engine,
    engine_classes,
    load_frames,
    reset_engine,
    reset_flags,
)

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path("C:/TensorRT/TensorRT-11.2.1.2/bin")
TEXTURE_DLL = ROOT / "out/ovda-device-texture-spike" / "ovda_device_texture_spike.dll"


class TexturePost(SourcePost):
    def __init__(self, engine, width, height, policy, diagnostic, dll_path=TEXTURE_DLL):
        super().__init__(engine, width, height, policy, dll_path)
        self.texture_handle = None
        try:
            self.dll.live_texture_error.restype = ct.c_char_p
            self.dll.live_texture_create.argtypes = [ct.c_int, ct.c_int]
            self.dll.live_texture_create.restype = ct.c_void_p
            self.dll.live_texture_publish.argtypes = [
                ct.c_void_p,
                ct.c_void_p,
                ct.c_float,
                ct.c_float,
                ct.c_int,
                ct.c_void_p,
                ct.c_int,
                ct.c_int,
            ]
            self.dll.live_texture_readback.argtypes = [
                ct.c_void_p,
                ct.c_int,
                ct.c_void_p,
            ]
            self.dll.live_texture_release.argtypes = [ct.c_void_p, ct.c_int]
            self.dll.live_texture_destroy.argtypes = [ct.c_void_p]
            self.texture_handle = self.dll.live_texture_create(width, height)
            self.texture_check(self.texture_handle)
            self.slot = 0
            self.output = (
                np.empty((height, width * 2, 4), np.uint8) if diagnostic else None
            )
        except BaseException:
            self.close()
            raise

    def texture_check(self, value):
        if not value:
            raise RuntimeError(self.dll.live_texture_error().decode("utf-8"))

    def render_texture(self, frame, depth, *, reset, diagnostic=False):
        if diagnostic != (self.output is not None):
            raise ValueError("Texture diagnostic contract changed")
        self.submit_post(frame, depth, device=True, reset=reset)
        slot = self.slot
        self.texture_check(
            self.dll.live_texture_publish(
                self.texture_handle,
                self.handle,
                self.policy.convergence,
                max(1.0, self.width * self.policy.divergence),
                int(self.policy.conservative_stereo_coverage),
                None,
                slot,
                0,
            )
        )
        if diagnostic:
            self.texture_check(
                self.dll.live_texture_readback(
                    self.texture_handle, slot, self.output.ctypes.data
                )
            )
        else:
            self.texture_check(self.dll.live_texture_release(self.texture_handle, slot))
        self.slot = 1 - slot
        return self.output

    def close(self):
        texture, self.texture_handle = self.texture_handle, None
        primary = None
        if texture:
            try:
                self.texture_check(self.dll.live_texture_destroy(texture))
            except Exception as error:
                primary = error
        try:
            super().close()
        except Exception as error:
            if primary is None:
                primary = error
            else:
                primary.add_note(str(error))
        if primary is not None:
            raise primary


def run_path(Engine, source, flags, policy, texture):
    engine = create_engine(Engine)
    samples = []
    try:
        engine.reset("start")
        post_type = TexturePost if texture else SourcePost
        post_args = (False,) if texture else ()
        with post_type(
            engine, source[0].shape[1], source[0].shape[0], policy, *post_args
        ) as post:
            began = time.perf_counter()
            for index, (frame, reset) in enumerate(zip(source, flags)):
                reset_engine(engine, reset, index)
                started = time.perf_counter()
                token = engine.infer_device(frame)
                try:
                    if texture:
                        post.render_texture(frame, token, reset=reset)
                    else:
                        post.render(frame, token, device=True, reset=reset)
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
    from screento3d_app.live_policy import resolve_live

    policy = resolve_live("video-quality")
    flags = reset_flags(source, policy.scene_cut_threshold)
    HostEngine, DeviceEngine, _ = engine_classes()
    hashes = {
        "host_output_dll": hashlib.sha256(HOST_OUTPUT_DLL.read_bytes()).hexdigest(),
        "texture_dll": hashlib.sha256(TEXTURE_DLL.read_bytes()).hexdigest(),
    }
    manifest = json.loads(
        (TEXTURE_DLL.parent / "build-manifest.json").read_text(encoding="utf-8-sig")
    )
    if hashes["texture_dll"].lower() != manifest["dll_sha256"].lower():
        raise ValueError("Texture DLL checksum mismatch")
    report = {
        "passed": False,
        "input": str(args.input.resolve()),
        "input_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "hashes": hashes,
        "mode": policy.name,
        "frames_per_run": len(source),
        "scene_reset_indices": [index for index, reset in enumerate(flags) if reset],
        "parity": {},
        "rows": [],
        "scope": (
            "Decoded host RGB -> owned oVDA device depth -> CUDA post/SBS -> "
            "two-slot D3D11 shared texture. Timed texture consumer only acquires/releases "
            "the keyed mutex and performs no pixel readback. RGB upload, model input "
            "preprocessing, synchronization and a CPU consumer command remain; zero_copy=false."
        ),
    }

    def save():
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    save()
    with ExitStack() as stack:
        stack.enter_context(os.add_dll_directory(str(RUNTIME)))
        host = create_engine(HostEngine)
        device = create_engine(DeviceEngine)
        exact = alpha = 0
        maximum = 0
        try:
            host.reset("start")
            device.reset("start")
            with (
                SourcePost(host, width, height, policy) as expected_post,
                TexturePost(device, width, height, policy, True) as texture_post,
            ):
                for index, (frame, reset) in enumerate(zip(source[:12], flags[:12])):
                    reset_engine(host, reset, index)
                    reset_engine(device, reset, index)
                    eyes = expected_post.render(
                        frame, host.infer(frame), device=False, reset=reset
                    )
                    expected = np.concatenate(eyes, axis=1)
                    token = device.infer_device(frame)
                    try:
                        actual = texture_post.render_texture(
                            frame, token, reset=reset, diagnostic=True
                        )
                    finally:
                        device.complete_device(token)
                    frame_exact = np.array_equal(actual[:, :, :3], expected)
                    exact += int(frame_exact)
                    alpha += int(np.all(actual[:, :, 3] == 255))
                    maximum = max(
                        maximum,
                        int(
                            np.max(np.abs(actual[:, :, :3].astype(np.int16) - expected))
                        ),
                    )
                    if not frame_exact:
                        raise AssertionError(f"Texture SBS mismatch at frame {index}")
        finally:
            host.close()
            device.close()
        report["parity"] = {
            "frames": 12,
            "exact_sbs_frames": exact,
            "opaque_alpha_frames": alpha,
            "maximum_channel_error": maximum,
        }
        save()
        print(json.dumps(report["parity"]), flush=True)

        paths = (
            ("device-depth-host-sbs", False),
            ("device-depth-shared-texture", True),
        )
        for round_index in range(args.repeats + 1):
            ordered = paths if round_index % 2 == 0 else tuple(reversed(paths))
            for execution_index, (name, texture) in enumerate(ordered):
                wall, samples, telemetry = run_path(
                    DeviceEngine, source, flags, policy, texture
                )
                row = {
                    "round": round_index,
                    "execution_index": execution_index,
                    "warmup": round_index == 0,
                    "path": name,
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
        report["summary"] = {
            name: {
                "median_fps": statistics.median(
                    row["fps"]
                    for row in report["rows"]
                    if row["path"] == name and not row["warmup"]
                ),
                "runs": args.repeats,
            }
            for name, _ in paths
        }
        host_fps = report["summary"]["device-depth-host-sbs"]["median_fps"]
        texture_fps = report["summary"]["device-depth-shared-texture"]["median_fps"]
        report["summary"]["texture_change_percent"] = (texture_fps / host_fps - 1) * 100
        report["transfer_accounting_per_60_frames"] = {
            "depth_d2h_bytes_avoided": width * height * 4 * 60,
            "host_sbs_d2h_bytes_avoided": width * height * 3 * 2 * 60,
        }
        report["passed"] = True
        save()
        print(json.dumps(report["summary"], indent=2), flush=True)


if __name__ == "__main__":
    main()
