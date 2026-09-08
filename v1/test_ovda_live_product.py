"""Real-engine parity/lifecycle check for the integrated oVDA live GPU path."""

import argparse
import hashlib
import json
import os
from contextlib import ExitStack
from pathlib import Path

import numpy as np

from test_ovda_device_post import (
    SourcePost,
    create_engine,
    engine_classes,
    load_frames,
    reset_engine,
    reset_flags,
)

from depthsbs_app.live_gpu_candidate import DLL_PATH, DLL_SHA256
from depthsbs_app.live_policy import resolve_live
from depthsbs_app.live_source_gpu_candidate import LiveSourceGpuCandidate


RUNTIME = Path("C:/TensorRT/TensorRT-11.2.1.2/bin")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Fresh output required")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    frames = load_frames(args.input, 12)
    policy = resolve_live("video-quality")
    flags = reset_flags(frames, policy.scene_cut_threshold)
    HostEngine, DeviceEngine, _ = engine_classes()
    dll_hash = hashlib.sha256(DLL_PATH.read_bytes()).hexdigest()
    if dll_hash != DLL_SHA256:
        raise ValueError("Product live DLL checksum mismatch")
    report = {
        "passed": False,
        "input": str(args.input.resolve()),
        "input_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "dll_sha256": dll_hash,
        "frames": len(frames),
        "exact_sbs_frames": 0,
        "maximum_channel_error": 0,
        "background_refinement_frames": 0,
    }
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    with ExitStack() as stack:
        stack.enter_context(os.add_dll_directory(str(RUNTIME)))
        host = create_engine(HostEngine)
        device = create_engine(DeviceEngine)
        try:
            host.reset("start")
            device.reset("start")
            with (
                SourcePost(host, frames[0].shape[1], frames[0].shape[0], policy, DLL_PATH) as reference,
                LiveSourceGpuCandidate(
                    frames[0].shape[1], frames[0].shape[0], policy, device
                ) as product,
            ):
                for index, (frame, reset) in enumerate(zip(frames, flags)):
                    reset_engine(host, reset, index)
                    reset_engine(device, reset, index)
                    if reset and index:
                        product.reset()
                    expected = reference.render(
                        frame, host.infer(frame), device=False, reset=reset
                    )
                    report["background_refinement_frames"] += int(
                        product.needs_background(frame)
                    )
                    actual = product.render(frame, product.infer(frame))
                    error = max(
                        int(np.max(np.abs(left.astype(np.int16) - right)))
                        for left, right in zip(expected, np.split(actual, 2, axis=1))
                    )
                    report["maximum_channel_error"] = max(
                        report["maximum_channel_error"], error
                    )
                    report["exact_sbs_frames"] += int(error == 0)
                    if error:
                        raise AssertionError(f"Integrated oVDA mismatch at frame {index}")
                telemetry = device.telemetry()
                if telemetry["pending_device_depth"]:
                    raise AssertionError("Device depth remained pending")
                if telemetry["device_depth_completions"] != len(frames):
                    raise AssertionError("Device depth completion count mismatch")
                report["telemetry"] = telemetry
        finally:
            host.close()
            device.close()
    report["passed"] = True
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
