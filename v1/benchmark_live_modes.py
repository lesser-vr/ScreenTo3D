"""Public-video live benchmark: five repeats, actual output clock readback.

Readback probes are separate from throughput windows; not motion-to-photon.
"""

import argparse
import binascii
import ctypes
import csv
import hashlib
import json
import os
import platform
import subprocess
import time
from collections import deque
from pathlib import Path

import numpy as np
import cv2
import shiboken6
from PySide6.QtGui import QColor, QPainter, QImage
from test_live_preview import Oracle
from depthsbs_app.desktop import create_app
from depthsbs_app.live_policy import LIVE_MODES
from depthsbs_app.live_sbs import DEFAULT_CAPTURE_INTERVAL_MS
from depthsbs_app.live_gpu_candidate import DLL_PATH, DEFAULT_RESOLVE
from depthsbs_app.capture_telemetry import observation_rates
from benchmark_guard import OutputRateGuard


class ClockOracle(Oracle):
    def __init__(self, source="generated"):
        super().__init__()
        self.stamps = deque(maxlen=4096)
        self.video = None
        self.video_frame = None
        self.video_frames = 0
        self.paint_count = 0
        if source != "generated":
            from public_test_media import CORPUS

            self.video = cv2.VideoCapture(str(CORPUS / f"{source}.mp4"))
            if not self.video.isOpened():
                raise ValueError("Prepared public video unavailable")
            self.setWindowTitle(f"DepthSBS public test: {source}")

    def advance(self):
        if self.video is not None:
            ok, frame = self.video.read()
            if not ok:
                self.video.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = self.video.read()
            if not ok:
                raise RuntimeError("Public video decode failed")
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self.video_frame = QImage(
                rgb.data,
                rgb.shape[1],
                rgb.shape[0],
                rgb.strides[0],
                QImage.Format_RGB888,
            ).copy()
            self.video_frames += 1
        super().advance()

    def paintEvent(self, event):
        self.paint_count += 1
        super().paintEvent(event)
        p = QPainter(self)
        if self.video_frame is not None:
            p.drawImage(self.rect(), self.video_frame)
        stamp = time.perf_counter_ns() // 1_000_000
        self.stamps.append(stamp)
        crc = binascii.crc_hqx(stamp.to_bytes(6, "little"), 0)
        value = (stamp << 16) | crc
        for bit in range(64):
            p.fillRect(
                24 + bit * 6,
                8,
                6,
                20,
                QColor("white" if value & (1 << bit) else "black"),
            )


def memory_bytes(pid):
    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("faults", ctypes.c_ulong)] + [
            (name, ctypes.c_size_t)
            for name in (
                "peak_ws",
                "ws",
                "peak_paged",
                "paged",
                "peak_nonpaged",
                "nonpaged",
                "pagefile",
                "peak_pagefile",
                "private",
            )
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    psapi.GetProcessMemoryInfo.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(Counters),
        ctypes.c_ulong,
    ]
    handle = kernel.OpenProcess(0x1000 | 0x10, False, pid)
    if not handle:
        raise OSError("Cannot sample owned worker memory")
    try:
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            raise OSError("Memory sample failed")
        return int(counters.private)
    finally:
        kernel.CloseHandle(handle)


def decode_output(image, width, height, dpi):
    image = image.convertToFormat(QImage.Format_RGB888)
    array = (
        np.frombuffer(image.bits(), np.uint8)
        .reshape(image.height(), image.bytesPerLine())[:, : image.width() * 3]
        .reshape(image.height(), image.width(), 3)
    )
    fit = min(image.width() / (2 * width), image.height() / height)
    ox, oy = (image.width() - width * 2 * fit) / 2, (image.height() - height * fit) / 2
    # Search bounded disparity offsets; CRC rejects warped/misaligned bit rows.
    found = set()
    for shift in range(-int(width * 0.025), int(width * 0.025) + 1):
        xs = np.rint(ox + ((24 + np.arange(64) * 6 + 3) * dpi + shift) * fit).astype(
            int
        )
        y = round(oy + 18 * dpi * fit)
        if xs.min() < 0 or xs.max() >= image.width():
            continue
        bits = (array[y, xs] > 200).all(axis=1)
        value = sum(int(bit) << index for index, bit in enumerate(bits))
        stamp, crc = value >> 16, value & 65535
        if stamp and binascii.crc_hqx(stamp.to_bytes(6, "little"), 0) == crc:
            found.add(stamp)
    return next(iter(found)) if len(found) == 1 else None


def process_cpu_seconds(pid):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.GetProcessTimes.argtypes = [ctypes.c_void_p] + [
        ctypes.POINTER(ctypes.c_ulonglong)
    ] * 4
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        raise OSError("Cannot sample owned worker CPU")
    try:
        values = [ctypes.c_ulonglong() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(v) for v in values)):
            raise OSError("Owned worker CPU sample failed")
        return (values[2].value + values[3].value) / 10_000_000
    finally:
        kernel.CloseHandle(handle)


def summary(values):
    return (
        {f"p{q}": float(np.percentile(values, q)) for q in (50, 95, 99)}
        if values
        else None
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=6)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--startup-timeout", type=float, default=120)
    parser.add_argument("--sizes", default="1280x720,1920x1080")
    parser.add_argument("--modes", default=",".join(LIVE_MODES))
    parser.add_argument(
        "--video-model",
        choices=("vda-small", "ovda-small-c16"),
        default="vda-small",
        help="Explicit Video Quality backend",
    )
    parser.add_argument(
        "--ovda-noncommercial",
        action="store_true",
        help="Confirm oVDA personal/non-commercial license conditions",
    )
    parser.add_argument(
        "--source",
        choices=("generated", "FloorballGame", "OfficeWalk", "ParkingGarage"),
        default="FloorballGame",
    )
    parser.add_argument("--hz", type=int, choices=(0, 30, 60), default=0)
    parser.add_argument('--uncapped', action='store_true',
        help='Diagnostic only: no presentation deadline, 1ms polling, request Qt vsync off')
    parser.add_argument('--gpu-replay', action='store_true',
        help='Diagnostic only: bounded public GPU frame replay; excludes real capture and source painting')
    parser.add_argument('--source-interval-ms', type=int, choices=range(0,1001), default=16,
        metavar='0..1000', help='Owned source timer; 0 advances as quickly as the source process can run')
    parser.add_argument("--poll-ms", type=int, choices=(1, 2, 4, 8))
    parser.add_argument("--hide-main", action="store_true")
    parser.add_argument("--sample-gpu", action="store_true")
    parser.add_argument("--capture-telemetry", action="store_true")
    parser.add_argument("--profile-gui", action="store_true")
    parser.add_argument("--source-process", action="store_true")
    parser.add_argument(
        "--save-review-frames",
        action="store_true",
        help="Save the 15 post-measurement output readbacks for visual review",
    )
    parser.add_argument("--abort-output-below-fps", type=float)
    parser.add_argument("--path", choices=("gpu", "reference", "gpu-texture"))
    parser.add_argument(
        "--guide-candidate", choices=("rolling", "hybrid", "promoted")
    )
    parser.add_argument(
        "--input-candidate",
        choices=("pinned",),
        help="Opt-in native RGB input staging candidate",
    )
    parser.add_argument(
        "--capture-candidate",
        choices=("retained",),
        help="Opt-in retained mapped capture-frame candidate",
    )
    parser.add_argument(
        "--legacy-poll",
        action="store_true",
        help="Explicit old 33ms scheduling baseline",
    )
    args = parser.parse_args()
    if args.gpu_replay:
        if (not args.uncapped or args.path != 'gpu-texture' or not args.source_process or
                args.source == 'generated' or args.capture_telemetry or args.guide_candidate or
                args.input_candidate or args.capture_candidate or
                any(mode not in ('performance','balanced') for mode in args.modes.split(','))):
            raise ValueError('GPU replay requires uncapped native Small/Base, isolated public source and no other candidate')
        from benchmark_gpu_replay import sbs_worker_replay
        from depthsbs_app import live_sbs as live_sbs_module
        os.environ['DEPTHSBS_BENCH_REPLAY_SOURCE'] = args.source
        os.environ['DEPTHSBS_GPU_CAPTURE'] = '1'
        live_sbs_module.sbs_worker = sbs_worker_replay
    if args.startup_timeout <= 0:
        raise ValueError("Positive startup timeout required")
    if args.abort_output_below_fps is not None and args.abort_output_below_fps <= 0:
        raise ValueError("Positive output guard threshold required")
    if args.capture_telemetry:
        os.environ["DEPTHSBS_CAPTURE_TELEMETRY"] = "1"
    if args.guide_candidate and args.path != "gpu-texture":
        raise ValueError("Guide candidate integration is scoped to gpu-texture")
    if args.input_candidate and args.path != "gpu-texture":
        raise ValueError("Input candidate integration is scoped to gpu-texture")
    if args.capture_candidate and args.path != "gpu-texture":
        raise ValueError("Capture candidate integration is scoped to gpu-texture")
    if args.guide_candidate and args.input_candidate:
        raise ValueError("Run one isolated candidate at a time")
    if args.capture_candidate and (args.guide_candidate or args.input_candidate):
        raise ValueError("Run one isolated candidate at a time")
    guide_candidate = None
    if args.guide_candidate == "rolling":
        from depthsbs_app import live_sbs as live_sbs_module
        from depthsbs_app.live_guide_rolling_worker import (
            candidate_manifest,
            sbs_worker_rolling,
        )

        guide_candidate = candidate_manifest()
        live_sbs_module.sbs_worker = sbs_worker_rolling
    elif args.guide_candidate == "hybrid":
        from depthsbs_app import live_sbs as live_sbs_module
        from depthsbs_app.live_guide_hybrid_worker import (
            candidate_manifest,
            sbs_worker_hybrid,
        )

        guide_candidate = candidate_manifest()
        live_sbs_module.sbs_worker = sbs_worker_hybrid
    elif args.guide_candidate == "promoted":
        from depthsbs_app import live_sbs as live_sbs_module
        from depthsbs_app.live_guide_promoted_worker import (
            candidate_manifest,
            sbs_worker_promoted,
        )

        guide_candidate = candidate_manifest()
        live_sbs_module.sbs_worker = sbs_worker_promoted
    input_candidate = None
    if args.input_candidate == "pinned":
        from depthsbs_app import live_sbs as live_sbs_module
        from depthsbs_app.live_pinned_input_worker import (
            candidate_manifest,
            sbs_worker_pinned_input,
        )

        input_candidate = candidate_manifest()
        live_sbs_module.sbs_worker = sbs_worker_pinned_input
    capture_candidate = None
    if args.capture_candidate == "retained":
        from depthsbs_app import live_sbs as live_sbs_module
        from depthsbs_app.live_retained_capture_worker import (
            candidate_manifest,
            sbs_worker_retained_capture,
        )

        capture_candidate = candidate_manifest()
        live_sbs_module.sbs_worker = sbs_worker_retained_capture
    args.output.mkdir(parents=True, exist_ok=False)
    if args.uncapped:
        if args.legacy_poll:
            raise ValueError('Uncapped and legacy pacing are mutually exclusive')
        from PySide6.QtGui import QSurfaceFormat
        os.environ['QSG_NO_VSYNC'] = '1'
        surface = QSurfaceFormat.defaultFormat()
        surface.setSwapInterval(0)
        QSurfaceFormat.setDefaultFormat(surface)
    app, engine, desktop = create_app()
    live = desktop.live
    raw_output_swaps = [0]
    live.output_window.frameSwapped.connect(
        lambda: raw_output_swaps.__setitem__(0, raw_output_swaps[0] + 1)
    )
    public_sources = None
    if args.source != "generated":
        from public_test_media import prepare

        public_sources = prepare()
    from live_benchmark_source import SourceProcess

    oracle = None
    rows = []
    gpu_sampler = None
    gpu_log = None
    gui_profiler = None
    output_guard = None

    def output_count():
        current = live.report()
        return (
            current["native_delivery"]["output"]["submitted_frames"]
            if current["native_delivery"] is not None
            else current["output_frame_swaps"]
        )

    if args.profile_gui:
        import cProfile

        gui_profiler = cProfile.Profile()
        gui_profiler.enable()

    def pump(seconds):
        end = time.perf_counter() + seconds
        while time.perf_counter() < end:
            if isinstance(oracle, SourceProcess):
                oracle.check()
            app.processEvents()
            if output_guard is not None and output_guard.due(time.perf_counter()):
                alert = output_guard.observe(time.perf_counter(), output_count())
                if alert is not None:
                    alert["action"] = (
                        "Stop; notify user and wait for monitor-on confirmation. No automatic retry or causal experiments."
                    )
                    (args.output / "stop-alert.json").write_text(
                        json.dumps(alert, indent=2), encoding="utf-8"
                    )
                    live.stop()
                    raise RuntimeError(f"Output rate guard stopped benchmark: {alert}")
            # Do not impose a coarser benchmark loop than the app's 1ms timer.
            time.sleep(0.0005 if live.cadence.poll_ms == 1 else 0.002)

    def wait(predicate, timeout=120):
        end = time.perf_counter() + timeout
        while not predicate() and time.perf_counter() < end:
            pump(0.03)
        assert predicate(), {"status": live.status, "report": live.report()}

    def command(*argv):
        return subprocess.check_output(
            argv, creationflags=subprocess.CREATE_NO_WINDOW, text=True
        ).strip()

    try:
        if args.source_process:
            oracle = SourceProcess(args.source, interval_ms=args.source_interval_ms)
            if args.gpu_replay:
                oracle.request('pause')  # Source window is only an owned geometry placeholder.
        else:
            oracle = ClockOracle(args.source)
            if args.source_interval_ms != 16:
                from PySide6.QtCore import Qt
                oracle.timer.setTimerType(Qt.PreciseTimer)
                oracle.timer.setInterval(args.source_interval_ms)
            oracle.show()
        gpu_preflight = command(
            "nvidia-smi",
            "--query-gpu=name,utilization.gpu,memory.used,temperature.gpu,power.draw",
            "--format=csv,noheader",
        )
        gpu_processes_preflight = command(
            "nvidia-smi",
            "--query-compute-apps=pid,process_name,used_gpu_memory",
            "--format=csv,noheader",
        )
        if args.sample_gpu:
            gpu_log = (args.output / "gpu-samples.csv").open("w", encoding="utf-8")
            gpu_sampler = subprocess.Popen(
                [
                    "nvidia-smi",
                    "--query-gpu=timestamp,index,utilization.gpu,utilization.memory,memory.used,power.draw,temperature.gpu,clocks.sm",
                    "--format=csv,noheader,nounits",
                    "--loop-ms=1000",
                ],
                stdout=gpu_log,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        pump(0.4)
        dpi = oracle.devicePixelRatioF()
        for size in args.sizes.split(","):
            width, height = map(int, size.split("x"))
            oracle.resize(round(width / dpi), round(height / dpi))
            pump(0.3)
            for mode in args.modes.split(","):
                live.items = [
                    dict(
                        kind="window",
                        id=int(oracle.winId()),
                        pid=oracle.pid if args.source_process else os.getpid(),
                        label=f"Test source: {args.source}",
                        width=width,
                        height=height,
                    )
                ]
                live.selected = 0
                live.setSbs(True)
                live.setMode(mode)
                if mode == "video-quality":
                    live.setLiveModel(args.video_model)
                    if args.video_model == "ovda-small-c16":
                        live.setOvdaConfirmed(args.ovda_noncommercial)
                live.setPresentationHz(0 if args.uncapped else args.hz)
                if args.path:
                    live.setProcessingPath(args.path)
                    assert live.processingPath == args.path, live.status
                if args.legacy_poll:
                    if args.hz != 30:
                        raise ValueError("Legacy baseline is 30 Hz only")
                    live.timer.setInterval(33)
                    # Old timer alone paced submissions; no additional deadline gate.
                    live.cadence.period_ns = 0
                if args.hide_main and not desktop.main_window.isVisible():
                    # Native delivery is demand-driven. Prime every new session
                    # with one visible consumer before hiding the diagnostic UI.
                    desktop.main_window.showNormal()
                    pump(0.1)
                live.start()
                assert live.active, live.status
                # The minimal shell has no in-app result consumer.
                # Prime the actual output consumer before waiting for frames.
                live.showOutput(0, False)
                live.output_window.resize(1400, 650)
                if args.poll_ms is not None:
                    if args.legacy_poll:
                        raise ValueError(
                            "Cannot combine poll override with legacy pacing"
                        )
                    live.timer.setInterval(args.poll_ms)
                wait(
                    lambda: live.submitted >= 8 or not live.active,
                    args.startup_timeout,
                )
                assert live.active, live.status
                if args.abort_output_below_fps is not None:
                    output_guard = OutputRateGuard(
                        args.abort_output_below_fps, time.perf_counter(), output_count()
                    )
                if args.hide_main:
                    desktop.main_window.hide()
                    live.setPreviewVisible(False)
                pump(args.seconds)  # discarded warmup window
                assert live.active and live.process is not None, live.status
                for repeat in range(args.repeats):
                    source_start = oracle.refresh() if args.source_process else None
                    before = live.report()
                    raw_before = raw_output_swaps[0]
                    source_before = (oracle.sequence, oracle.paint_count)
                    began = time.perf_counter()
                    cpu_began = time.process_time()
                    worker_cpu_began = process_cpu_seconds(live.process.pid)
                    wall_began_ns = time.time_ns()
                    mem = []
                    gui_mem = []
                    stages = []
                    gpu_stages = []
                    projection_stages = []
                    host_stages = []
                    qt_stages = []
                    capture_events = []
                    capture_missing_snapshots = 0
                    capture_before = before["capture_telemetry"]
                    capture_last = capture_before["callbacks"] if capture_before else 0
                    while time.perf_counter() - began < args.seconds:
                        pump(0.25)
                        assert live.active, live.status
                        mem.append(
                            [
                                time.perf_counter() - began,
                                memory_bytes(live.process.pid),
                            ]
                        )
                        stages.append(live._stats()[3:7])
                        gpu_stages.append(live._stats()[12:20])
                        projection_stages.append(live._stats()[24:30])
                        host_stages.append(live._stats()[20:24])
                        gui_mem.append(memory_bytes(os.getpid()))
                        qt_stages.append((live.gui_copy_ms, live.gui_notify_ms))
                        if live.capture_telemetry is not None:
                            snapshot = live.capture_telemetry.snapshot(history=True)
                            if snapshot is None:
                                capture_missing_snapshots += 1
                            else:
                                capture_events.extend(
                                    event
                                    for event in snapshot["events"]
                                    if event[0] > capture_last
                                )
                                capture_last = snapshot["callbacks"]
                    after = live.report()
                    elapsed = time.perf_counter() - began
                    source_end = oracle.refresh() if args.source_process else None
                    source_elapsed = (
                        (source_end["observed_ns"] - source_start["observed_ns"]) / 1e9
                        if args.source_process
                        else elapsed
                    )
                    assert (after["width"], after["height"]) == (width * 2, height)
                    if gpu_sampler is not None:
                        assert gpu_sampler.poll() is None, "GPU sampler exited"
                    if args.gpu_replay:
                        after['source_clock'] = 'Synthetic GPU replay submission time; no WGC or encoded source clock'
                        after['copies'] = 'Cached public BGRA GPU clone + ordinary GPU preprocessing/depth/SBS/native delivery; excludes WGC and window painting'
                        after['received_scope'] = 'Pulled GPU replay sequence'
                    row = dict(
                        size=size,
                        mode=mode,
                        repeat=repeat,
                        input_kind='gpu-public-replay' if args.gpu_replay else 'window-capture',
                        inference_fps=(after['inference_frames']-before['inference_frames'])/elapsed,
                        reused_depth_fps=(after['reused_depth_frames']-before['reused_depth_frames'])/elapsed,
                        seconds=elapsed,
                        wall_start_ns=wall_began_ns,
                        wall_end_ns=time.time_ns(),
                        worker_cpu_seconds=process_cpu_seconds(live.process.pid)
                        - worker_cpu_began,
                        raw_output_swap_callback_fps=(raw_output_swaps[0] - raw_before)
                        / elapsed,
                        image_provider_request_fps=(
                            after["qt_delivery"]["provider_requests"]
                            - before["qt_delivery"]["provider_requests"]
                        )
                        / elapsed,
                        gui_cpu_seconds=time.process_time() - cpu_began,
                        gui_private_bytes=gui_mem,
                        source_advance_fps=(oracle.sequence - source_before[0])
                        / source_elapsed,
                        source_paint_fps=(oracle.paint_count - source_before[1])
                        / source_elapsed,
                        source_observation_start=source_start,
                        source_observation_end=source_end,
                        source_cpu_seconds=(
                            source_end["cpu_seconds"] - source_start["cpu_seconds"]
                            if args.source_process
                            else None
                        ),
                        source_private_bytes=memory_bytes(oracle.pid)
                        if args.source_process
                        else None,
                        capture_arrival_fps=(after["received"] - before["received"])
                        / elapsed,
                        capture_arrival_scope=("Pulled cached GPU frames; not WGC capture arrivals" if args.gpu_replay else
                            "Legacy forwarded/cached sequence proxy; use capture_observation_rates for independent Python callbacks"),
                        capture_observation_rates=observation_rates(
                            capture_before, after["capture_telemetry"]
                        ),
                        capture_observation_start=capture_before,
                        capture_events=capture_events,
                        capture_missing_snapshots=capture_missing_snapshots,
                        gui_submission_fps=(after["submitted"] - before["submitted"])
                        / elapsed,
                        processed_fps=(
                            after["processed_frames"] - before["processed_frames"]
                        )
                        / elapsed,
                        output_swap_fps=(
                            after["native_delivery"]["output"]["submitted_frames"]
                            - before["native_delivery"]["output"]["submitted_frames"]
                            if after["native_delivery"] is not None
                            else after["output_frame_swaps"]
                            - before["output_frame_swaps"]
                        )
                        / elapsed,
                        output_rate_kind="distinct native afterFrameEnd IDs"
                        if after["native_delivery"] is not None
                        else "host callback submission proxy",
                        native_main_fps=(
                            after["native_delivery"]["main"]["submitted_frames"]
                            - before["native_delivery"]["main"]["submitted_frames"]
                        )
                        / elapsed
                        if after["native_delivery"] is not None
                        else None,
                        replacements=after["processing_stats"][1]
                        - before["processing_stats"][1],
                        memory=mem,
                        stage_samples_ns=stages,
                        gpu_stage_samples_ns=gpu_stages,
                        projection_stage_samples_ns=projection_stages,
                        host_bridge_samples_ns=host_stages,
                        qt_delivery_samples_ms=qt_stages,
                        report=after,
                    )
                    rows.append(row)
                    (args.output / "runs.json").write_text(
                        json.dumps(rows, indent=2), encoding="utf-8"
                    )
                    print(
                        json.dumps(
                            {
                                k: row[k]
                                for k in (
                                    "size",
                                    "mode",
                                    "repeat",
                                    "processed_fps",
                                    "output_swap_fps",
                                )
                            }
                        ),
                        flush=True,
                    )
                # Intentional readback/overload probes are not throughput windows.
                output_guard = None
                ages = []
                attempts = 0
                review_frames = []
                review_root = args.output / "review" / f"{size}-{mode}"
                if args.save_review_frames:
                    review_root.mkdir(parents=True)
                for review_index in range(0 if args.gpu_replay else 15):
                    pump(0.2)
                    rendered = live.output_window.grabWindow()
                    observed = time.perf_counter_ns() / 1e6
                    stamp = decode_output(rendered, width, height, dpi)
                    attempts += 1
                    if args.source_process:
                        oracle.refresh()
                    if stamp in oracle.stamps and 0 <= observed - stamp < 2000:
                        ages.append(observed - stamp)
                    if args.save_review_frames:
                        review_path = review_root / f"frame-{review_index:03d}.png"
                        if not rendered.save(str(review_path), "PNG"):
                            raise RuntimeError("Failed to save review output frame")
                        review_frames.append(
                            {
                                "path": str(review_path),
                                "sha256": hashlib.sha256(
                                    review_path.read_bytes()
                                ).hexdigest(),
                                "source_stamp_ms": stamp,
                                "observed_ms": observed,
                                "age_ms": observed - stamp
                                if stamp in oracle.stamps
                                else None,
                            }
                        )
                rows[-1]["paint_to_output_readback_ms"] = ages
                rows[-1]["clock_attempts"] = attempts
                rows[-1]["clock_summary_ms"] = summary(ages)
                rows[-1]["review_frames"] = review_frames
                # Native slots backpressure production; host output can overwrite.
                slow_interval = max(200, round(3000 / rows[-1]["processed_fps"]))
                live.timer.setInterval(slow_interval)
                old = live.report()
                pump(max(3, slow_interval / 1000 * 4))
                new = live.report()
                if live.nativeEnabled:
                    replaced = new["processing_stats"][1] - old["processing_stats"][1]
                    if not args.gpu_replay:
                        assert replaced > 0, "backpressure must replace capture input"
                    assert new["native_delivery"]["live_pools"] <= 3
                    assert new["native_delivery"]["live_nodes"] <= 2
                    assert len(live.native.frames) <= 2
                    replacement_boundary = "gpu_replay_pull_backpressure" if args.gpu_replay else "capture_input"
                else:
                    replaced = new["replaced"] - old["replaced"]
                    assert replaced > 0, "overload must replace pending output"
                    replacement_boundary = "host_output"
                assert new["pending_frame"] <= 1
                rows[-1]["overload"] = dict(
                    poll_interval_ms=slow_interval,
                    replaced=replaced,
                    replacement_boundary=replacement_boundary,
                    pending=new["pending_frame"],
                    slots=new["mailbox_slots"],
                )
                live.timer.setInterval(live.cadence.poll_ms)
                live.stop()
                # Keep the output scene exposed briefly so its NativeSurface can
                # observe the stopped session and delete the old render node.
                # Hiding first prevents that cleanup frame from being rendered.
                pump(0.15)
                if live.nativeEnabled:
                    live.output_window.grabWindow()
                wait(lambda: not live.active, 15)
                if args.hide_main:
                    # The hidden main NativeSurface cannot run updatePaintNode
                    # to delete its old node. Expose one stopped/blank frame only
                    # after measurement so the next session cannot retain it.
                    desktop.main_window.showNormal()
                    pump(0.15)
                    desktop.main_window.grabWindow()
                # Let QML/render-thread visibility and native-session teardown
                # settle before creating another CUDA/WGC worker in this process.
                # Immediate back-to-back starts can otherwise leave the next
                # worker blocked during GPU/capture initialization even though
                # the previous child has exited.
                pump(0.25)
                if live.nativeEnabled:
                    native_after_stop = live.native.report()
                    assert native_after_stop["live_pools"] == 0
                    assert native_after_stop["live_nodes"] == 0
                    rows[-1]["native_after_stop"] = native_after_stop
                live.output_window.hide()
                if args.hide_main:
                    desktop.main_window.hide()
                pump(0.1)
                (args.output / "runs.json").write_text(
                    json.dumps(rows, indent=2), encoding="utf-8"
                )
        from depthsbs_app.desktop_jobs import BUNDLE
        import PySide6

        selected_models = sorted(
            {row["report"]["plan"]["model"] for row in rows if row["report"]["plan"]}
        )
        environment = dict(
            gpu_preflight=gpu_preflight,
            gpu_processes_preflight=gpu_processes_preflight,
            benchmark_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            os=platform.platform(),
            python=platform.python_version(),
            qt=PySide6.__version__,
            gpu=command(
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.total,power.draw,clocks.sm",
                "--format=csv,noheader",
            ),
            commit=command("git", "rev-parse", "HEAD"),
            dirty=bool(command("git", "status", "--porcelain")),
            model_ids=selected_models,
            video_model=args.video_model if "video-quality" in args.modes.split(",") else None,
            ovda_noncommercial_confirmed=(
                args.ovda_noncommercial and "ovda-small-c16" in selected_models
            ),
            model_sha256=(
                hashlib.sha256(
                    (BUNDLE / "models/da2-small/model_fp16.onnx").read_bytes()
                ).hexdigest()
                if selected_models == ["da2-small"]
                else None
            ),
            model_hash_scope=(
                "DA2 Small ONNX"
                if selected_models == ["da2-small"]
                else "Non-Small bindings validated their trusted local plan manifests before startup"
            ),
            dpi=dpi,
            fixture=args.source,
            source_process=args.source_process,
            source_pid=oracle.pid if args.source_process else os.getpid(),
            source_harness_sha256=hashlib.sha256(
                Path("v1/live_benchmark_source.py").read_bytes()
            ).hexdigest(),
            public_sources=public_sources,
            public_video_decoded_frames=oracle.video_frames,
            presentation_target_hz=0 if args.uncapped else args.hz,
            uncapped_diagnostic=args.uncapped,
            gpu_replay=args.gpu_replay,
            gpu_replay_frames=60 if args.gpu_replay else None,
            gpu_replay_sha256=hashlib.sha256(Path('v1/benchmark_gpu_replay.py').read_bytes()).hexdigest() if args.gpu_replay else None,
            source_process_sha256=hashlib.sha256(Path('v1/live_benchmark_source.py').read_bytes()).hexdigest(),
            source_interval_ms=args.source_interval_ms,
            legacy_poll=args.legacy_poll,
            diagnostic_poll_ms=args.poll_ms,
            diagnostic_hide_main=args.hide_main,
            live_capture_interval_ms=int(
                os.environ.get(
                    "DEPTHSBS_LIVE_CAPTURE_INTERVAL_MS",
                    str(DEFAULT_CAPTURE_INTERVAL_MS),
                )
            ),
            profile_source="live_policy.py",
            host_bridge=os.environ.get("DEPTHSBS_LIVE_HOST_BRIDGE", "fused"),
            base_input_preprocessing=os.environ.get('DEPTHSBS_BASE_INPUT', 'gpu'),
            gpu_capture=os.environ.get('DEPTHSBS_GPU_CAPTURE', 'model/source default'),
            base_input_dll_sha256=hashlib.sha256(Path('out/base-input/base_input.dll').read_bytes()).hexdigest()
                if 'da2-base' in selected_models and os.environ.get('DEPTHSBS_BASE_INPUT', 'gpu') == 'gpu' else None,
            small_input_dll_sha256=hashlib.sha256(Path('out/small-input/small_input.dll').read_bytes()).hexdigest()
                if 'da2-small' in selected_models and os.environ.get('DEPTHSBS_GPU_CAPTURE', '1') == '1' and live.processingPath != 'reference' else None,
            gpu_capture_dll_sha256=hashlib.sha256(Path('out/gpu-capture/gpu_capture.dll').read_bytes()).hexdigest()
                if any(model in selected_models for model in ('da2-base','da2-small')) and os.environ.get('DEPTHSBS_GPU_CAPTURE', '1') == '1' and live.processingPath != 'reference' else None,
            diagnostic_profile=bool(os.environ.get("DEPTHSBS_LIVE_PROFILE")),
            live_path=live.processingPath,
            live_dll_sha256=(
                guide_candidate["dll_sha256"]
                if guide_candidate is not None
                else hashlib.sha256(DLL_PATH.read_bytes()).hexdigest()
            )
            if live.processingPath in ("gpu", "gpu-texture")
            else None,
            guide_candidate=guide_candidate,
            input_candidate=input_candidate,
            capture_candidate=capture_candidate,
            native_dll_sha256=live.native.report()["dll_sha256"]
            if live.nativeEnabled
            else None,
            texture_runtime_sha256=hashlib.sha256(
                Path("out/live-texture-runtime/live_texture_runtime.dll").read_bytes()
            ).hexdigest()
            if live.nativeEnabled
            else None,
            resolve_impl=os.environ.get("DEPTHSBS_LIVE_RESOLVE", DEFAULT_RESOLVE),
            base_cuda_graph=os.environ.get('DEPTHSBS_BASE_GRAPH', '0'),
            stereo_renderer=os.environ.get('DEPTHSBS_STEREO_RENDERER','cuda'),
            learned_renderer_artifacts=(dict(
                source_revision='0d3d92c8f4396da564c44524b6390ee5c76b9668',
                weight_sha256=hashlib.sha256(Path('out/iw3-render-models-20261105/iw3_row_flow_v3_sym_20250628.pth').read_bytes()).hexdigest(),
                bridge_sha256=hashlib.sha256(Path('out/rowflow-bridge/rowflow_bridge.dll').read_bytes()).hexdigest(),
            ) if os.environ.get('DEPTHSBS_STEREO_RENDERER')=='rowflow-sym' else None),
            base_stage_profile=os.environ.get('DEPTHSBS_BASE_STAGE_PROFILE', '0'),
            source_sha256={
                str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in [
                    Path("v1/depthsbs_app") / name
                    for name in (
                        "live_sbs.py",
                        "rowflow.py",
                        "gpu_capture.py",
                        "gpu_frame.py",
                        "gpu_runtime.py",
                        "live_model.py",
                        "base_gpu_input.py",
                        "small_gpu_input.py",
                        "live_small_gpu_input.py",
                        "da2_base_device.py",
                        "desktop.py",
                        "capture_worker.py",
                        "capture_telemetry.py",
                        "live_preview.py",
                        "owned_preview_image.py",
                        "live_host_bridge.py",
                        "live_policy.py",
                        "live_gpu_candidate.py",
                        "live_guide_hybrid_worker.py",
                        "live_guide_promoted_worker.py",
                        "live_guide_rolling_worker.py",
                        "live_pinned_input.py",
                        "live_pinned_input_worker.py",
                        "live_retained_capture.py",
                        "live_retained_capture_worker.py",
                        "live_scene_history.py",
                        "live_gpu_texture.py",
                        "live_texture_pool.py",
                        "native_delivery.py",
                        "presentation_policy.py",
                        "texture_mailbox.py",
                        "trt_backend.py",
                        "pipeline.py",
                    )
                ]
            },
            qml_sha256=hashlib.sha256(
                Path("v1/depthsbs_app/qml/Main.qml").read_bytes()
            ).hexdigest(),
            warmup_seconds=args.seconds,
            gpu_sample_scope="Device-wide 1s samples, includes desktop/source and other workloads; not process attribution"
            if args.sample_gpu
            else None,
            cpu_scope=(
                "GUI excludes separately owned source decode/paint; source CPU uses child observation bounds; worker CPU is owned SBS process"
                if args.source_process
                else "GUI process includes public source decode/paint; worker CPU is owned SBS process; seconds/elapsed is core-equivalent usage"
            ),
            capture_telemetry=os.environ.get("DEPTHSBS_CAPTURE_TELEMETRY", "0") == "1",
            diagnostic_gui_profile=args.profile_gui,
            abort_output_below_fps=args.abort_output_below_fps,
            qsg_no_vsync=os.environ.get("QSG_NO_VSYNC"),
            qsg_render_loop=os.environ.get("QSG_RENDER_LOOP"),
            capture_event_fields=[
                "callback",
                "entry_ns",
                "exit_ns",
                "source_ns",
                "outcome",
            ],
            capture_event_outcomes={"0": "published", "1": "contention", "2": "failed"},
            note="Short local source-window runs. Output readback is separate and not photon latency; inspect fixture/provenance and idle preflight.",
        )
        (args.output / "environment.json").write_text(json.dumps(environment, indent=2))
        fields = (
            "size",
            "mode",
            "repeat",
            "seconds",
            "processed_fps",
            "output_swap_fps",
            "output_rate_kind",
            "native_main_fps",
            "gui_cpu_seconds",
            "worker_cpu_seconds",
            "image_provider_request_fps",
        )
        with (args.output / "runs.csv").open(
            "w", newline="", encoding="utf-8"
        ) as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    except BaseException as error:
        (args.output / 'failure.json').write_text(json.dumps(dict(
            error=repr(error), status=live.status, report=live.report(),
        ), indent=2), encoding='utf-8')
        raise
    finally:
        if gpu_sampler is not None:
            gpu_sampler.terminate()
            try:
                gpu_sampler.wait(timeout=5)
            except subprocess.TimeoutExpired:
                gpu_sampler.kill()
                gpu_sampler.wait(timeout=5)
        if gpu_log is not None:
            gpu_log.close()
        try:
            live.stop()
            # Cleanup must not depend on a failed source still being alive.
            deadline = time.perf_counter() + 15
            while live.active and time.perf_counter() < deadline:
                app.processEvents()
                time.sleep(0.002)
            assert not live.active, live.status
        finally:
            try:
                if oracle is not None:
                    oracle.close()
                    if not args.source_process and oracle.video is not None:
                        oracle.video.release()
            finally:
                shiboken6.delete(engine)
        if gui_profiler is not None:
            gui_profiler.disable()
            gui_profiler.dump_stats(str(args.output / "gui.pstats"))


if __name__ == "__main__":
    main()
