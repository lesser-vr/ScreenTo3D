"""Bounded VFG presentation metadata and D3D consumer; no CUDA imports."""
import time
import ctypes as ct
from .texture_mailbox import TextureMailbox, RETIRING
from .native_delivery import NativeDelivery

from dataclasses import dataclass


@dataclass
class Timeline:
    previous_source: int | None = None
    last_due: int = 0

    def plan(self, source: int, ready: int, reset: bool):
        if source <= 0 or ready <= 0 or source - ready > 100_000_000:
            raise ValueError("Invalid source/ready clock")
        interval = source - self.previous_source if self.previous_source is not None else 0
        interpolate = not reset and 0 < interval <= 100_000_000
        # Preserve actual ready/source times when fast WGC processing finishes
        # before the compositor stamp; schedule after both without clock clamping.
        first = max(ready, source, self.last_due + 1)
        if first - ready > 100_000_000:
            raise RuntimeError("VFG presentation backlog exceeded bound")
        if interpolate:
            result = ((1, first, self.previous_source + interval // 2, self.previous_source),
                      (0, first + interval // 2, source, source))
        else:
            result = ((0, first, source, source),)
        self.previous_source, self.last_due = source, result[-1][1]
        return result


class TimedMailbox(TextureMailbox):
    @classmethod
    def create(cls, context):
        base = super().create(context)
        base.timing = context.RawArray(ct.c_longlong, 16)  # 8 words per existing slot.
        return base

    def publish_timed(self, frame, due, oldest, kind, base_id, ready):
        # WGC's compositor timestamp can lead CPU completion on fast paths.
        # Preserve both clocks; only the scheduled output must follow both.
        # Bound that lead so malformed timestamps cannot retain a slot forever.
        if (kind not in (0,1) or not 0 < oldest <= frame.source_ns <= due
                or not 0 < ready <= due or frame.source_ns - ready > 100_000_000):
            raise ValueError(f"Invalid VFG timing: source-to-ready={ready-frame.source_ns}ns, callback-to-ready={ready-frame.callback_ns}ns, ready-to-due={due-ready}ns, kind={kind}")
        if frame.slot not in self.writable_slots(frame.session, frame.generation):
            raise ValueError("VFG output slot is still leased")
        self._acquire()
        try:
            offset = frame.slot * 8
            self.timing[offset:offset+8] = [frame.sequence, due, frame.source_ns, oldest,
                                           kind, base_id, ready, frame.callback_ns]
        finally:
            self.lock.release()
        super().publish(frame)

    def frame_timing(self, frame):
        self._acquire()
        try:
            record = tuple(self.timing[frame.slot*8:frame.slot*8+8])
            if record[0] != frame.sequence:
                raise RuntimeError("Stale VFG timing descriptor")
            return record
        finally:
            self.lock.release()

    def publish(self, frame):
        now = time.perf_counter_ns()
        return self.publish_timed(frame, max(now, frame.source_ns), frame.source_ns, 0, frame.sequence, now)


class TimedDelivery(NativeDelivery):
    vfg_delivery = True
    def __init__(self):
        super().__init__()
        self.records = {}
        self.visible = lambda: True
        self.on_published = lambda: None

    def begin(self, session):
        super().begin(session)
        self.records.clear()

    def frame_due_ns(self, mailbox, frame):
        return mailbox.frame_timing(frame)[1]

    def frame_origin(self, frame):
        record = self.records.get(frame.sequence)
        if record is not None:
            return record[2], record[4]

    def consume(self, mailbox, owned_pid, *, cadence=None):
        delivery = self

        class Cadence:
            period_ns = 1  # One descriptor per poll; avoids same-poll replacement.

            def ready(self, now):
                pending = [f for f in mailbox.pending(delivery.pool.session, delivery.pool.generation)
                           if f.sequence > delivery.last_sequence]
                if not pending:
                    return False
                record = mailbox.frame_timing(pending[0])
                if record[1] > now or cadence is not None and not cadence.ready(now):
                    return False
                if delivery.visible() and delivery.has_frame:
                    submitted = delivery.report()["output"]["last_submitted_id"]
                    if submitted < delivery.last_sequence:
                        return False
                delivery.records[record[0]] = record
                if len(delivery.records) > 4096:
                    del delivery.records[min(delivery.records)]
                return True

            def emitted(self, now):
                if cadence is not None:
                    cadence.emitted(now)

        if self.pool is not None and mailbox.state() == RETIRING:
            # Retirement must consume/release all pending GPU leases, regardless of due times.
            return super().consume(mailbox, owned_pid)
        changed = super().consume(mailbox, owned_pid, cadence=Cadence())
        if changed:
            self.on_published()
        return changed
