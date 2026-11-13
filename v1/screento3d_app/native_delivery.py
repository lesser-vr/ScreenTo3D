"""Explicit pure-D3D11 Qt consumer. Importing this module never imports CUDA."""
from .messages import ErrorMessage as E


import ctypes as ct
import hashlib
import time
from collections import OrderedDict

from .desktop_jobs import ROOT
from .texture_mailbox import OFFERED, RETIRING

NATIVE_SHA256 = "fa26607ef3e0e773caa52acffa2f4712255cf1a56165179c688a9c77ce6226ef"
_registered = None


def load_native():
    global _registered
    if _registered is not None:
        return _registered
    from PySide6.QtCore import qVersion

    if qVersion() != "6.10.2":
        raise RuntimeError(E('E_OUTPUT_QT_VERSION'))
    path = ROOT / "out/qt-native-delivery/qt_native_delivery.dll"
    if hashlib.sha256(path.read_bytes()).hexdigest() != NATIVE_SHA256:
        raise RuntimeError("Native Qt delivery DLL checksum mismatch")
    dll = ct.CDLL(str(path))
    uid = ct.c_ulonglong
    dll.native_begin.argtypes = [uid]
    dll.native_install.argtypes = [
        uid,
        uid,
        ct.c_ulong,
        uid,
        uid,
        ct.c_int,
        ct.c_int,
        ct.c_ulong,
        ct.c_long,
    ]
    dll.native_publish.argtypes = [uid, uid, ct.c_int, uid]
    dll.native_releases.argtypes = [ct.POINTER(uid)]
    dll.native_metrics.argtypes = [ct.POINTER(uid)]
    dll.native_output_samples.argtypes = [uid, ct.POINTER(uid), ct.c_uint]
    dll.native_error.restype = ct.c_char_p
    for name in ("native_retire", "native_drop_pool", "native_end"):
        getattr(dll, name).restype = None
    if not dll.native_register():
        raise RuntimeError("Cannot register native Qt surface")
    _registered = dll
    return dll


class NativeDelivery:
    def __init__(self):
        self.dll = load_native()
        self.pool = None
        self.frames = {}
        self.last_sequence = 0
        self.has_frame = False
        self.retiring = False
        self.session = 0
        self._samples = (ct.c_ulonglong * (4096 * 2))()

    def check(self, code=1):
        error = self.dll.native_error()
        if error or not code:
            raise RuntimeError(
                error.decode("utf-8", "replace") if error else "Native delivery failed"
            )

    def begin(self, session):
        self.session = session
        self.output_timing = OrderedDict()
        self.pool = None
        self.frames.clear()
        self.last_sequence = 0
        self.has_frame = self.retiring = False
        self.check(self.dll.native_begin(session))

    def _releases(self, mailbox):
        released = (ct.c_ulonglong * 2)()
        self.check(self.dll.native_releases(released))
        for slot, sequence in enumerate(released):
            frame = self.frames.get(slot)
            if frame is not None and sequence == frame.sequence:
                mailbox.release(frame)
                del self.frames[slot]

    def consume(self, mailbox, owned_pid, *, cadence=None):
        """Pace publication only; always service errors, GPU releases and retirement."""
        self.check()
        state = mailbox.state()
        changed = False
        if state == OFFERED and self.pool is None:
            pool = mailbox.offered(session=self.session, owned_pid=owned_pid)
            if pool is not None:
                self.check(
                    self.dll.native_install(
                        pool.session,
                        pool.generation,
                        pool.origin_pid,
                        *pool.handles,
                        pool.width,
                        pool.height,
                        pool.luid_low,
                        pool.luid_high,
                    )
                )
                mailbox.install(pool.session, pool.generation)
                self.pool = pool
                self.retiring = False
        if self.pool is None:
            return changed
        pool = self.pool
        self._releases(mailbox)
        retiring = mailbox.state() == RETIRING
        for frame in mailbox.pending(pool.session, pool.generation):
            if frame.sequence <= self.last_sequence:
                continue
            if not retiring and cadence is not None and not cadence.ready(time.perf_counter_ns()):
                break
            if frame.slot in self.frames:
                raise RuntimeError("Native frame overwrote a pending slot")
            timing = self.frame_origin(frame)
            self.output_timing[frame.sequence] = timing
            if len(self.output_timing) > 8192:
                self.output_timing.popitem(last=False)
            self.check(
                self.dll.native_publish(
                    frame.session, frame.generation, frame.slot, frame.sequence
                )
            )
            self.frames[frame.slot] = frame
            self.last_sequence = frame.sequence
            self.has_frame = changed = True
            if not retiring and cadence is not None:
                cadence.emitted(time.perf_counter_ns())
                if cadence.period_ns:
                    break  # Never publish both slots at a single capped deadline.
        if mailbox.state() == RETIRING:
            # Retirement may race this poll. Drain unpublished GPU leases on the
            # next poll before dropping the pool; metadata alone cannot free them.
            if any(frame.sequence > self.last_sequence
                   for frame in mailbox.pending(pool.session, pool.generation)):
                return changed
            self.dll.native_retire()
            self.has_frame = False
            changed = True
            self.retiring = True
        self._releases(mailbox)
        if self.retiring and not self.frames:
            self.dll.native_drop_pool()
            mailbox.finish_retirement(pool.session, pool.generation)
            self.pool = None
            self.retiring = False
        return changed

    def end(self):
        self.dll.native_end()
        self.pool = None
        self.frames.clear()
        self.has_frame = False

    def frame_due_ns(self, mailbox, frame):
        return 0

    def frame_origin(self, frame):
        return frame.source_ns, 0

    def recent_output(self, since):
        count = self.dll.native_output_samples(since, self._samples, len(self._samples) // 2)
        samples = []
        for index in range(0, count * 2, 2):
            origin = self.output_timing.get(self._samples[index + 1])
            if origin is not None:
                samples.append((self._samples[index], *origin))
        return samples

    def next_poll_delay_ns(self, mailbox, cadence, now):
        """Only retry for pending GPU releases, retirement or a timed frame.

        The retained current frame alone never causes polling. Producer state
        changes wake the GUI separately; the health timer remains a fallback.
        """
        if self.pool is None:
            return None
        if self.retiring or len(self.frames) > 1 or mailbox.state() == RETIRING:
            return 1_000_000
        pending = [f for f in mailbox.pending(self.pool.session, self.pool.generation)
                   if f.sequence > self.last_sequence]
        if not pending:
            return None
        due = max(cadence.next_ns, self.frame_due_ns(mailbox, pending[0]))
        return max(1_000_000, due - now)

    def report(self):
        values = (ct.c_ulonglong * 12)()
        self.dll.native_metrics(values)
        names = (
            "uploaded_frames",
            "last_uploaded_id",
            "submitted_frames",
            "last_submitted_id",
            "copy_ns",
        )
        return dict(
            main=dict(zip(names, values[:5])),
            output=dict(zip(names, values[5:10])),
            live_pools=values[10],
            live_nodes=values[11],
            dll_sha256=NATIVE_SHA256,
            scope="Distinct Qt afterFrameEnd IDs, not physical display; GPU copy includes mutex wait",
        )
