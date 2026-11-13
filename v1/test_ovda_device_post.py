"""Compare host and owned-device oVDA depth through the same CUDA SBS consumer."""

import argparse
import ctypes as ct
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
DLL = ROOT / "out/ovda-device-post-spike/live_depth.dll"


def load_frames(path, limit=60):
    capture = cv2.VideoCapture(str(path))
    values = []
    try:
        while len(values) < limit:
            ok, frame = capture.read()
            if not ok:
                break
            values.append(np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
    finally:
        capture.release()
    if len(values) != limit:
        raise ValueError("Input frame count is shorter than requested")
    return values


def engine_classes():
    from screento3d_app import ovda

    host = ovda.runtime_class()
    from _screento3d_ovda.device_depth import OvdaBufferedDeviceTrt, OvdaDeviceTrt

    return host, OvdaDeviceTrt, OvdaBufferedDeviceTrt


def create_engine(engine):
    return engine(
        directory=ROOT / "out/ovda-local/518x924-fp32",
        runtime_dir=RUNTIME,
        profile=(518, 924),
    )


def reset_flags(frames, threshold):
    from screento3d_app.live_scene_history import LiveSceneHistory

    history = LiveSceneHistory(threshold)
    flags = []
    for index, frame in enumerate(frames):
        observation = history.inspect(frame)
        flags.append(index == 0 or observation.cut)
        history.commit(observation)
    return flags


class SourcePost:
    def __init__(self, engine, width, height, policy, dll_path=DLL, stream=None):
        self.engine = engine
        self.width, self.height, self.policy = width, height, policy
        self.stream = int(engine.stream.cuda_stream if stream is None else stream)
        if not self.stream:
            raise ValueError("Device-post stream is required")
        self.dll = ct.CDLL(str(dll_path))
        self.dll.live_create.argtypes = [
            ct.POINTER(ct.c_void_p),
            ct.c_int,
            ct.c_int,
            ct.c_void_p,
        ]
        self.dll.live_destroy.argtypes = [ct.c_void_p]
        self.dll.live_set_parallel.argtypes = [ct.c_void_p, ct.c_int]
        self.dll.live_post_source.argtypes = [
            ct.c_void_p,
            ct.c_void_p,
            ct.c_void_p,
            ct.c_int,
            ct.c_int,
            ct.c_double,
            ct.c_float,
            ct.c_float,
            ct.c_int,
            ct.c_void_p,
            ct.c_double,
        ]
        self.dll.live_project.argtypes = (
            [ct.c_void_p] * 2 + [ct.c_float, ct.c_float, ct.c_int] + [ct.c_void_p] * 3
        )
        self.handle = ct.c_void_p()
        self.check(
            self.dll.live_create(
                ct.byref(self.handle),
                width,
                height,
                self.stream,
            )
        )
        self.check(self.dll.live_set_parallel(self.handle, 1))

    @staticmethod
    def check(code):
        if code:
            raise RuntimeError(f"Device-post CUDA failure: {code}")

    def render(self, frame, depth, *, device, reset):
        self.submit_post(frame, depth, device=device, reset=reset)
        return self.project()

    def render_pointer(self, frame, pointer, *, producer_stream, reset):
        if int(producer_stream) != self.stream or not int(pointer):
            raise ValueError("Device-depth pointer must use the post stream")
        self._submit_pointer(frame, int(pointer), device=True, reset=reset)
        return self.project()

    def project(self):
        shape = (self.height, self.width, 3)
        left, right = np.empty(shape, np.uint8), np.empty(shape, np.uint8)
        invalid = ct.c_int()
        self.check(
            self.dll.live_project(
                self.handle,
                None,
                self.policy.convergence,
                max(1.0, self.width * self.policy.divergence),
                int(self.policy.conservative_stereo_coverage),
                left.ctypes.data,
                right.ctypes.data,
                ct.byref(invalid),
            )
        )
        if invalid.value:
            raise RuntimeError("Non-finite source depth")
        return left, right

    def submit_post(self, frame, depth, *, device, reset):
        self._validate_frame(frame)
        if device:
            depth.validate()
            if depth.owner is not self.engine:
                raise ValueError("Foreign device-depth token")
            pointer = depth.pointer
        else:
            if (
                not isinstance(depth, np.ndarray)
                or depth.dtype != np.float32
                or depth.shape != (1, self.height, self.width)
                or not depth.flags.c_contiguous
            ):
                raise ValueError("Invalid host depth")
            pointer = depth.ctypes.data
        self._submit_pointer(frame, pointer, device=device, reset=reset)

    def _validate_frame(self, frame):
        if frame.dtype != np.uint8 or frame.shape != (
            self.height,
            self.width,
            3,
        ):
            raise ValueError("Invalid source RGB")

    def _submit_pointer(self, frame, pointer, *, device, reset):
        self._validate_frame(frame)
        self.check(
            self.dll.live_post_source(
                self.handle,
                frame.ctypes.data,
                pointer,
                int(device),
                self.policy.depth_guide_radius,
                self.policy.temporal_alpha,
                self.policy.temporal_color_threshold,
                self.policy.temporal_depth_threshold,
                int(reset),
                None,
                self.policy.temporal_depth_transition,
            )
        )

    def close(self):
        handle, self.handle = self.handle, ct.c_void_p()
        if handle.value:
            self.check(self.dll.live_destroy(handle))

    def __enter__(self):
        return self

    def __exit__(self, kind, primary, tb):
        try:
            self.close()
        except Exception as error:
            if primary is None:
                raise
            primary.add_note(str(error))


def reset_engine(engine, reset, index):
    if reset and index:
        engine.reset("scene_cut")


def run_path(Engine, source, flags, policy, device):
    engine = create_engine(Engine)
    elapsed = []
    try:
        engine.reset("start")
        with SourcePost(engine, source[0].shape[1], source[0].shape[0], policy) as post:
            began = time.perf_counter()
            for index, (frame, reset) in enumerate(zip(source, flags)):
                reset_engine(engine, reset, index)
                started = time.perf_counter()
                if device:
                    depth = engine.infer_device(frame)
                    try:
                        post.render(frame, depth, device=True, reset=reset)
                    finally:
                        engine.complete_device(depth)
                else:
                    post.render(frame, engine.infer(frame), device=False, reset=reset)
                elapsed.append((time.perf_counter() - started) * 1000)
            wall = time.perf_counter() - began
        telemetry = engine.telemetry()
    finally:
        engine.close()
    return wall, elapsed, telemetry


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
    HostEngine, DeviceEngine, BufferedEngine = engine_classes()
    manifest = json.loads(
        (DLL.parent / "build-manifest.json").read_text(encoding="utf-8-sig")
    )
    dll_hash = hashlib.sha256(DLL.read_bytes()).hexdigest()
    if dll_hash.lower() != manifest["dll_sha256"].lower():
        raise ValueError("Device-post DLL checksum mismatch")
    report = {
        "passed": False,
        "input": str(args.input.resolve()),
        "input_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "dll": str(DLL.resolve()),
        "dll_sha256": dll_hash,
        "mode": policy.name,
        "frames_per_run": len(source),
        "scene_reset_indices": [index for index, reset in enumerate(flags) if reset],
        "parity": {},
        "rows": [],
        "scope": (
            "Decoded RGB -> oVDA depth -> identical CUDA temporal/guided/SBS -> "
            "host SBS. Device path removes depth D2H/re-upload only; RGB input and "
            "SBS output remain host transfers, synchronization remains, flat-background "
            "CPU refinement is excluded, and zero_copy=false."
        ),
    }

    def save():
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    save()
    with ExitStack() as stack:
        stack.enter_context(os.add_dll_directory(str(RUNTIME)))
        host = create_engine(HostEngine)
        device = create_engine(DeviceEngine)
        buffered = create_engine(BufferedEngine)
        exact = {"device-depth": 0, "buffered-device-depth": 0}
        maximum = {"device-depth": 0, "buffered-device-depth": 0}
        try:
            host.reset("start")
            device.reset("start")
            buffered.reset("start")
            with (
                SourcePost(host, width, height, policy) as host_post,
                SourcePost(device, width, height, policy) as device_post,
                SourcePost(buffered, width, height, policy) as buffered_post,
            ):
                for index, (frame, reset) in enumerate(zip(source[:12], flags[:12])):
                    reset_engine(host, reset, index)
                    reset_engine(device, reset, index)
                    reset_engine(buffered, reset, index)
                    expected = host_post.render(
                        frame, host.infer(frame), device=False, reset=reset
                    )
                    for name, engine, post in (
                        ("device-depth", device, device_post),
                        ("buffered-device-depth", buffered, buffered_post),
                    ):
                        token = engine.infer_device(frame)
                        try:
                            actual = post.render(frame, token, device=True, reset=reset)
                        finally:
                            engine.complete_device(token)
                        frame_exact = all(
                            np.array_equal(left, right)
                            for left, right in zip(expected, actual)
                        )
                        exact[name] += int(frame_exact)
                        maximum[name] = max(
                            maximum[name],
                            max(
                                int(np.max(np.abs(left.astype(np.int16) - right)))
                                for left, right in zip(expected, actual)
                            ),
                        )
                        if not frame_exact:
                            raise AssertionError(
                                f"Host/{name} SBS mismatch at frame {index}"
                            )
        finally:
            host.close()
            device.close()
            buffered.close()
        report["parity"] = {"frames": 12}
        for name in exact:
            report["parity"][name] = {
                "exact_sbs_frames": exact[name],
                "maximum_channel_error": maximum[name],
            }
        save()
        print(json.dumps(report["parity"]), flush=True)

        for round_index in range(args.repeats + 1):
            paths = (
                ("host-depth", HostEngine, False),
                ("device-depth", DeviceEngine, True),
                ("buffered-device-depth", BufferedEngine, True),
            )
            rotation = round_index % len(paths)
            paths = paths[rotation:] + paths[:rotation]
            for execution_index, (name, Engine, device_path) in enumerate(paths):
                wall, samples, telemetry = run_path(
                    Engine, source, flags, policy, device_path
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
            for name in ("host-depth", "device-depth", "buffered-device-depth")
        }
        host_fps = report["summary"]["host-depth"]["median_fps"]
        device_fps = report["summary"]["device-depth"]["median_fps"]
        buffered_fps = report["summary"]["buffered-device-depth"]["median_fps"]
        report["summary"]["device_change_percent"] = (device_fps / host_fps - 1) * 100
        report["summary"]["buffered_change_from_device_percent"] = (
            buffered_fps / device_fps - 1
        ) * 100
        report["passed"] = True
        save()
        print(json.dumps(report["summary"], indent=2), flush=True)


if __name__ == "__main__":
    main()
