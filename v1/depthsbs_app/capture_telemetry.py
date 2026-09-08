"""Opt-in bounded Python-callback observations, not native WGC/readback timing."""

import ctypes
import time
from dataclasses import dataclass

CAPACITY = 256
FIELDS = 5  # callback ordinal, entry QPC ns, exit QPC ns, source ns, outcome
PUBLISHED, CONTENTION, FAILED = range(3)
SCOPE = (
    "Independent Python callback observations after native readback/GIL entry; "
    "not native WGC arrival or physical-display latency. Missing diagnostic "
    "events are counted, not interpolated. Source timestamps use a separate clock."
)


@dataclass
class CaptureTelemetry:
    state: object
    events: object
    lock: object
    session_id: int

    @classmethod
    def create(cls, context):
        return cls(
            context.RawArray(ctypes.c_longlong, 7),
            context.RawArray(ctypes.c_longlong, CAPACITY * FIELDS),
            context.Lock(),
            time.perf_counter_ns(),
        )

    def snapshot(self, *, history=False):
        if not self.lock.acquire(False):
            return None
        try:
            callbacks, published, contention, failed, missing, updated, complete = (
                self.state
            )
            result = dict(
                session_id=self.session_id,
                callbacks=callbacks,
                published=published,
                contention=contention,
                failed=failed,
                missing_events=missing,
                updated_ns=updated,
                snapshot_ns=time.perf_counter_ns(),
                complete=bool(complete),
                capacity=CAPACITY,
                scope=SCOPE,
            )
            if history:
                rows = [
                    list(self.events[i : i + FIELDS])
                    for i in range(0, CAPACITY * FIELDS, FIELDS)
                ]
                result["events"] = sorted(
                    (r for r in rows if max(0, callbacks - CAPACITY) < r[0]),
                    key=lambda r: r[0],
                )
                result["event_fields"] = [
                    "callback",
                    "entry_ns",
                    "exit_ns",
                    "source_ns",
                    "outcome",
                ]
            return result
        finally:
            self.lock.release()


class CaptureRecorder:
    """One capture-callback writer; counters survive a missed snapshot publish."""

    def __init__(self, shared):
        self.shared = shared
        self.counts = [0] * 7

    def observe(self, entry_ns, exit_ns, source_ns, outcome):
        if outcome not in (PUBLISHED, CONTENTION, FAILED):
            raise ValueError("Invalid capture observation outcome")
        self.counts[0] += 1
        self.counts[1 + outcome] += 1
        self.counts[5] = exit_ns
        if not self.shared.lock.acquire(False):
            self.counts[4] += 1
            return
        try:
            offset = ((self.counts[0] - 1) % CAPACITY) * FIELDS
            self.shared.events[offset : offset + FIELDS] = [
                self.counts[0],
                entry_ns,
                exit_ns,
                source_ns,
                outcome,
            ]
            self.shared.state[:] = self.counts
        finally:
            self.shared.lock.release()

    def finish(self):
        # Only after the capture control has stopped/joined its callback thread.
        # If the reader owns the lock, keep complete=false rather than block.
        if not self.shared.lock.acquire(False):
            return
        try:
            self.counts[6] = 1
            self.shared.state[:] = self.counts
        finally:
            self.shared.lock.release()


def observation_rates(before, after):
    """Rates use independent snapshot bounds, not forwarded GUI frame metadata."""
    if before is None or after is None:
        return None
    if before["session_id"] != after["session_id"]:
        raise ValueError("Capture observation session changed")
    elapsed = (after["snapshot_ns"] - before["snapshot_ns"]) / 1e9
    keys = ("callbacks", "published", "contention", "failed", "missing_events")
    differences = {key: after[key] - before[key] for key in keys}
    if elapsed <= 0 or any(value < 0 for value in differences.values()):
        raise ValueError("Capture observations belong to different/invalid windows")
    return dict(
        seconds=elapsed,
        **{f"{key}_fps": value / elapsed for key, value in differences.items()},
        snapshot_lag_ns=[
            s["snapshot_ns"] - s["updated_ns"] if s["updated_ns"] else None
            for s in (before, after)
        ],
        scope=SCOPE,
    )
