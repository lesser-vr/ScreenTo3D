"""Owned-source capture or explicit host-SBS diagnostic without product GUI."""

import argparse
import hashlib
import json
import multiprocessing as mp
import os
from pathlib import Path
import time

import numpy as np

from live_benchmark_source import SourceProcess
from depthsbs_app.capture_mailbox import (
    Mailbox,
    STATE,
    FAILED,
    STOPPED,
    WIDTH,
    HEIGHT,
    SEQ,
    ACK,
)
from depthsbs_app.capture_telemetry import CaptureTelemetry, observation_rates
from depthsbs_app.capture_worker import capture_worker
from depthsbs_app.live_sbs import sbs_worker, STAT_COUNT, PROCESSED


def consume_host(mailbox, buffer):
    """Copy under ownership, then ACK. Never acknowledge a partial/failed copy."""
    if not mailbox.lock.acquire(timeout=0.01):
        return False
    try:
        m = mailbox.meta
        if m[STATE] == FAILED:
            raise RuntimeError(mailbox.error.value.decode("utf-8"))
        if m[SEQ] <= m[ACK]:
            return False
        if (m[WIDTH], m[HEIGHT]) != (3840, 1080):
            raise ValueError("Unexpected host SBS dimensions")
        pixels = np.frombuffer(mailbox.pixels, np.uint8, count=buffer.size)
        np.copyto(buffer, pixels)
        m[ACK] = m[SEQ]
        return True
    finally:
        mailbox.lock.release()


def event_metrics(events):
    """Adjacent ordinals only; never bridge missing/overwritten ring entries."""
    durations = [(row[2] - row[1]) / 1e6 for row in events]
    pairs = [(a, b) for a, b in zip(events, events[1:]) if b[0] == a[0] + 1]

    def quantiles(values):
        return (
            {f"p{q}": float(np.percentile(values, q)) for q in (50, 95, 99)}
            if values
            else None
        )

    return dict(
        observed_events=len(events),
        adjacent_pairs=len(pairs),
        callback_duration_ms=quantiles(durations),
        callback_interval_ms=quantiles([(b[1] - a[1]) / 1e6 for a, b in pairs]),
        source_interval_ms=quantiles([(b[3] - a[3]) / 1e6 for a, b in pairs]),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=3)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--interval", type=int, choices=(0, 16), default=0)
    parser.add_argument("--sbs-host", action="store_true")
    args = parser.parse_args()
    if args.seconds <= 0 or args.repeats <= 0:
        raise ValueError("Positive duration/repeats required")
    args.output.mkdir(parents=True, exist_ok=False)
    context = mp.get_context("spawn")
    mailbox = Mailbox.create(context, sbs=args.sbs_host)
    stats = context.RawArray("q", STAT_COUNT)
    buffer = np.empty(3840 * 1080 * 4, np.uint8) if args.sbs_host else None
    consumed = 0
    telemetry = CaptureTelemetry.create(context)
    source = None
    capture = None
    report = dict(
        passed=False,
        rows=[],
        interval=args.interval,
        sbs_host=args.sbs_host,
        qsg_no_vsync=os.environ.get("QSG_NO_VSYNC"),
    )

    def health():
        nonlocal consumed
        source.check()
        if not capture.is_alive():
            raise RuntimeError(f"Capture exited: {capture.exitcode}")
        if mailbox.lock.acquire(timeout=0.1):
            try:
                if mailbox.meta[STATE] == FAILED:
                    raise RuntimeError(mailbox.error.value.decode("utf-8"))
            finally:
                mailbox.lock.release()
        if args.sbs_host:
            consumed += int(consume_host(mailbox, buffer))

    def snapshot():
        deadline = time.perf_counter() + 1
        while time.perf_counter() < deadline:
            value = telemetry.snapshot(history=True)
            if value is not None:
                return value
            time.sleep(0.002)
        raise TimeoutError("Capture diagnostic unavailable")

    try:
        source = SourceProcess("FloorballGame")
        dpi = source.devicePixelRatioF()
        source.resize(round(1920 / dpi), round(1080 / dpi))
        time.sleep(0.3)
        descriptor = dict(
            kind="window", id=source.winId(), pid=source.pid, width=1920, height=1080
        )
        report["source"] = descriptor
        if args.sbs_host:
            os.environ["DEPTHSBS_LIVE_CAPTURE_INTERVAL_MS"] = str(args.interval)
        capture = context.Process(
            target=sbs_worker if args.sbs_host else capture_worker,
            args=(descriptor, False, mailbox, stats, 1.0, "balanced", True)
            if args.sbs_host
            else (descriptor, False, mailbox),
            kwargs=dict(capture_telemetry=telemetry)
            if args.sbs_host
            else dict(
                minimum_update_interval=args.interval, capture_telemetry=telemetry
            ),
        )
        capture.start()
        report["capture_pid"] = capture.pid
        deadline = time.perf_counter() + 120
        while (stats[PROCESSED] if args.sbs_host else snapshot()["callbacks"]) < 3:
            health()
            if time.perf_counter() > deadline:
                raise TimeoutError("No capture frames")
            time.sleep(0.05)
        warmup_end = time.perf_counter() + args.seconds
        while time.perf_counter() < warmup_end:
            health()
            time.sleep(0.002 if args.sbs_host else 0.05)
        for repeat in range(args.repeats):
            source_before = source.refresh()
            before = snapshot()
            processed_before, consumed_before = stats[PROCESSED], consumed
            began = time.perf_counter()
            end = time.perf_counter() + args.seconds
            while time.perf_counter() < end:
                health()
                time.sleep(0.002 if args.sbs_host else 0.05)
            elapsed = time.perf_counter() - began
            processed_after, consumed_after = stats[PROCESSED], consumed
            after = snapshot()
            source_after = source.refresh()
            events = [row for row in after["events"] if row[0] > before["callbacks"]]
            seconds = (source_after["observed_ns"] - source_before["observed_ns"]) / 1e9
            row = dict(
                repeat=repeat,
                processed_fps=(processed_after - processed_before) / elapsed
                if args.sbs_host
                else None,
                consumed_fps=(consumed_after - consumed_before) / elapsed
                if args.sbs_host
                else None,
                worker_stats=list(stats) if args.sbs_host else None,
                source_paint_fps=(
                    source_after["paint_count"] - source_before["paint_count"]
                )
                / seconds,
                capture=observation_rates(before, after),
                metrics=event_metrics(events),
                before=before,
                after=after,
                source_before=source_before,
                source_after=source_after,
            )
            report["rows"].append(row)
            print(
                json.dumps(
                    {
                        k: v
                        for k, v in row.items()
                        if k
                        in (
                            "repeat",
                            "source_paint_fps",
                            "capture",
                            "metrics",
                            "processed_fps",
                            "consumed_fps",
                        )
                    }
                ),
                flush=True,
            )
        report["passed"] = True
    finally:
        try:
            if capture is not None and capture.pid is not None:
                mailbox.stop.set()
                capture.join(10)
                forced = capture.is_alive()
                if forced:
                    capture.terminate()
                    capture.join(5)
                if capture.is_alive():
                    capture.kill()
                    capture.join(5)
                report["capture_exitcode"] = capture.exitcode
                report["forced_stop"] = forced
                report["final_telemetry"] = telemetry.snapshot()
                if mailbox.lock.acquire(timeout=0.5):
                    try:
                        report["final_meta"] = list(mailbox.meta)
                        report["error"] = mailbox.error.value.decode("utf-8")
                        report["passed"] &= mailbox.meta[STATE] == STOPPED and (
                            mailbox.meta[WIDTH],
                            mailbox.meta[HEIGHT],
                        ) == (3840 if args.sbs_host else 1920, 1080)
                    finally:
                        mailbox.lock.release()
                else:
                    report["passed"] = False
                report["passed"] &= not forced and capture.exitcode == 0
        finally:
            if source is not None:
                source.close()
            report["scope"] = (
                "Owned source + production GPU SBS with host D2H and bounded copy-before-ACK consumer; no product GUI/native texture display. Not equivalent to native output, not photon timing."
                if args.sbs_host
                else "Owned source + production capture/readback/mailbox copy only; no ACK consumer, inference, SBS or output window. Replacement is expected. Not native WGC or photon timing."
            )
            report["sha256"] = {
                str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (
                    Path(__file__),
                    Path("v1/live_benchmark_source.py"),
                    Path("v1/depthsbs_app/capture_worker.py"),
                    Path("v1/depthsbs_app/live_sbs.py"),
                )
            }
            (args.output / "report.json").write_text(
                json.dumps(report, indent=2), encoding="utf-8"
            )
    assert report["passed"], report


if __name__ == "__main__":
    main()
