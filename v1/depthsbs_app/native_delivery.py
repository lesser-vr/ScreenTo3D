"""Explicit pure-D3D11 Qt consumer. Importing this module never imports CUDA."""

import ctypes as ct
import hashlib
import time

from .desktop_jobs import ROOT
from .texture_mailbox import OFFERED, RETIRING

NATIVE_SHA256 = "2b8f6581f0dd3e34f530f6495ee20910b42ff78b90116b6c9d27af294978942c"
_registered = None


def load_native():
    global _registered
    if _registered is not None:
        return _registered
    from PySide6.QtCore import qVersion

    if qVersion() != "6.10.2":
        raise RuntimeError("GPU 직접 출력은 검증된 Qt 6.10.2가 필요합니다.")
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

    def check(self, code=1):
        error = self.dll.native_error()
        if error or not code:
            raise RuntimeError(
                error.decode("utf-8", "replace") if error else "Native delivery failed"
            )

    def begin(self, session):
        self.session = session
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
