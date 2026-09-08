"""Exact parity and pure-depth timing for the isolated oVDA device token."""

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

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path("C:/TensorRT/TensorRT-11.2.1.2/bin")


def frames(path, limit):
    capture = cv2.VideoCapture(str(path))
    values = []
    try:
        while len(values) < limit:
            ok, frame = capture.read()
            if not ok:
                break
            values.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    finally:
        capture.release()
    if len(values) != limit:
        raise ValueError("Input frame count is shorter than requested")
    return values


def engine_classes():
    from depthsbs_app import ovda

    host = ovda.runtime_class()
    from _depthsbs_ovda.device_depth import OvdaDeviceTrt

    return host, OvdaDeviceTrt


def create(engine):
    return engine(
        directory=ROOT / "out/ovda-local/518x924-fp32",
        runtime_dir=RUNTIME,
        profile=(518, 924),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.output.exists() or args.repeats <= 0:
        raise ValueError("Fresh output and positive repeats required")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    source = frames(args.input, 60)
    HostEngine, DeviceEngine = engine_classes()
    report = dict(
        passed=False,
        input=str(args.input.resolve()),
        input_sha256=hashlib.sha256(args.input.read_bytes()).hexdigest(),
        parity={},
        rows=[],
        scope="Pure oVDA depth on decoded RGB; no SBS/live capture/output consumer. Device path retains host input and synchronization, so zero_copy=false.",
    )
    with ExitStack() as stack:
        stack.enter_context(os.add_dll_directory(str(RUNTIME)))
        host = create(HostEngine)
        try:
            host.reset("start")
            expected = [host.infer(frame) for frame in source[:12]]
        finally:
            host.close()
        device = create(DeviceEngine)
        maximum = 0.0
        exact = 0
        close = 0
        rejected_early_reuse = expired = 0
        try:
            device.reset("start")
            for frame, reference in zip(source[:12], expected):
                token = device.infer_device(frame)
                try:
                    try:
                        device.infer_device(frame)
                    except RuntimeError:
                        rejected_early_reuse += 1
                    else:
                        raise AssertionError("Pending device depth was reused")
                    # A diagnostic host reader is not the intended same-stream
                    # consumer, so it must explicitly wait before copying.
                    device.stream.synchronize()
                    actual = token.tensor.cpu().numpy().copy()
                    maximum = max(maximum, float(np.max(np.abs(actual - reference))))
                    exact += int(np.array_equal(actual, reference))
                    close += int(np.allclose(actual, reference, atol=0.001, rtol=0.001))
                finally:
                    device.complete_device(token)
                try:
                    token.validate()
                except RuntimeError:
                    expired += 1
                else:
                    raise AssertionError("Completed device depth remained valid")
        finally:
            device.close()
        report["parity"] = dict(
            frames=12,
            exact=exact,
            within_existing_tolerance=close,
            maximum_absolute_error=maximum,
            rejected_early_reuse=rejected_early_reuse,
            expired_after_complete=expired,
        )
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report["parity"]), flush=True)
        assert close == rejected_early_reuse == expired == 12

        for round_index in range(args.repeats + 1):
            for path in ("host", "device"):
                engine = create(DeviceEngine if path == "device" else HostEngine)
                samples = []
                try:
                    engine.reset("start")
                    began = time.perf_counter()
                    for frame in source:
                        started = time.perf_counter()
                        if path == "host":
                            result = engine.infer(frame)
                            assert result.shape == (1, 1080, 1920)
                        else:
                            token = engine.infer_device(frame)
                            token.validate()
                            engine.complete_device(token)
                        samples.append((time.perf_counter() - started) * 1000)
                    elapsed = time.perf_counter() - began
                    telemetry = engine.telemetry()
                finally:
                    engine.close()
                row = dict(
                    round=round_index,
                    warmup=round_index == 0,
                    path=path,
                    fps=len(source) / elapsed,
                    elapsed_seconds=elapsed,
                    mean_ms=statistics.mean(samples),
                    p95_ms=float(np.percentile(samples, 95)),
                    telemetry=telemetry,
                )
                report["rows"].append(row)
                args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
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
            path: {
                "median_fps": statistics.median(
                    row["fps"]
                    for row in report["rows"]
                    if row["path"] == path and not row["warmup"]
                ),
                "runs": args.repeats,
            }
            for path in ("host", "device")
        }
        report["passed"] = True
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
