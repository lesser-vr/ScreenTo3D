"""Experimental, metadata-only two-slot transport. No Qt/CUDA imports.

This is an IPC protocol, not GPU synchronization. The native consumer MUST return
the keyed mutex to key 0 before calling release(). A metadata acknowledgement
alone never establishes that GPU work has finished. All operations are bounded
lock attempts so a dead peer holding the lock cannot hang the controller.
"""

import ctypes
from dataclasses import dataclass

from .capture_mailbox import MAX_WIDTH, MAX_HEIGHT

EMPTY, OFFERED, INSTALLED, RETIRING, RETIRED, CLOSED = range(6)
_STATE, _SESSION, _GENERATION, _PID, _WIDTH, _HEIGHT = range(6)
_LOW, _HIGH, _HANDLE0, _HANDLE1, _LAST = range(6, 11)
_SLOT0, _SLOT1 = 11, 15  # sequence, released sequence, source ns, callback ns
WORD_COUNT = 19
MAX_INTEGER = (1 << 63) - 1


def _integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"Invalid texture {name}")


@dataclass(frozen=True)
class TexturePool:
    session: int
    generation: int
    origin_pid: int
    width: int  # Packed output dimensions, independent of stereo arrangement.
    height: int
    luid_low: int
    luid_high: int
    handles: tuple[int, int]  # Producer-local unnamed NT handles.

    def validate(self, session, owned_pid):
        for name in ("session", "generation"):
            _integer(getattr(self, name), 1, MAX_INTEGER, name)
        _integer(self.origin_pid, 1, (1 << 32) - 1, "origin PID")
        if self.session != session or self.origin_pid != owned_pid:
            raise ValueError("Texture descriptor is not from the owned session/worker")
        _integer(self.width, 16, MAX_WIDTH * 2, "width")
        _integer(self.height, 16, MAX_HEIGHT * 2, "height")
        if self.width * self.height > MAX_WIDTH * MAX_HEIGHT * 2:
            raise ValueError("Texture output exceeds the bounded stereo pixel count")
        _integer(self.luid_low, 0, (1 << 32) - 1, "LUID low")
        _integer(self.luid_high, -(1 << 31), (1 << 31) - 1, "LUID high")
        if type(self.handles) is not tuple or len(self.handles) != 2:
            raise ValueError("Exactly two texture handles are required")
        for handle in self.handles:
            _integer(handle, 1, MAX_INTEGER, "NT handle")
        if self.handles[0] == self.handles[1]:
            raise ValueError("Texture slots must have distinct handles")


@dataclass(frozen=True)
class TextureFrame:
    session: int
    generation: int
    slot: int
    sequence: int
    source_ns: int
    callback_ns: int


@dataclass
class TextureMailbox:
    words: object
    lock: object
    wake_writer: object = None

    def notify(self):
        # Advisory bounded notification, never a GPU completion acknowledgment.
        # A full nonblocking socket already contains an unread wakeup.
        if self.wake_writer is not None:
            try:
                self.wake_writer.send(b'\x01')
            except BlockingIOError:
                pass

    @classmethod
    def create(cls, context):
        return cls(context.RawArray(ctypes.c_longlong, WORD_COUNT), context.Lock())

    def _acquire(self):
        if not self.lock.acquire(timeout=0.05):
            raise TimeoutError("Texture metadata peer is busy or unavailable")

    def _identity(self, session, generation):
        _integer(session, 1, MAX_INTEGER, "session")
        _integer(generation, 1, MAX_INTEGER, "generation")
        if (self.words[_SESSION], self.words[_GENERATION]) != (session, generation):
            raise ValueError("Stale texture session or pool generation")

    def offer(self, pool, *, session, owned_pid):
        """Producer offers one pool; never overwrites a live/retiring pool."""
        pool.validate(session, owned_pid)
        self._acquire()
        try:
            w = self.words
            if w[_STATE] not in (EMPTY, RETIRED):
                raise RuntimeError("Previous texture pool has not retired")
            if w[_STATE] == RETIRED and (
                pool.session != w[_SESSION] or pool.generation <= w[_GENERATION]
            ):
                raise ValueError("Texture generation must advance in the same session")
            last = w[_LAST]
            w[:] = [
                OFFERED,
                pool.session,
                pool.generation,
                pool.origin_pid,
                pool.width,
                pool.height,
                pool.luid_low,
                pool.luid_high,
                *pool.handles,
                last,
                *([0] * 8),
            ]
        finally:
            self.lock.release()

        self.notify()

    def offered(self, *, session, owned_pid):
        """GUI validates before DuplicateHandle/OpenSharedResource, not afterwards."""
        self._acquire()
        try:
            w = self.words
            if w[_STATE] != OFFERED:
                return None
            pool = TexturePool(*w[1:8], tuple(w[8:10]))
            pool.validate(session, owned_pid)
            return pool
        finally:
            self.lock.release()

    def install(self, session, generation):
        """GUI calls only after successful native import and adapter/format checks."""
        self._acquire()
        try:
            self._identity(session, generation)
            if self.words[_STATE] != OFFERED:
                raise RuntimeError("Texture pool is not awaiting installation")
            self.words[_STATE] = INSTALLED
        finally:
            self.lock.release()

    def publish(self, frame):
        """Producer calls after CUDA signals key 1; at most two frames pending."""
        _integer(frame.slot, 0, 1, "slot")
        _integer(frame.sequence, 1, MAX_INTEGER, "sequence")
        for name in ("source_ns", "callback_ns"):
            _integer(getattr(frame, name), 0, MAX_INTEGER, name)
        self._acquire()
        try:
            self._identity(frame.session, frame.generation)
            w = self.words
            offset = (_SLOT0, _SLOT1)[frame.slot]
            if w[_STATE] != INSTALLED:
                raise RuntimeError("Texture pool is not installed")
            if w[offset] != w[offset + 1]:
                raise RuntimeError("Texture slot is still leased")
            if frame.sequence <= w[_LAST]:
                raise ValueError("Texture frame IDs must strictly increase")
            w[offset] = w[_LAST] = frame.sequence
            w[offset + 2], w[offset + 3] = frame.source_ns, frame.callback_ns
        finally:
            self.lock.release()

        self.notify()

    def writable_slots(self, session, generation):
        """Sole producer checks BEFORE enqueueing a GPU write, then waits key 0.

        Metadata availability is necessary but not sufficient for GPU ownership.
        The same producer owns retirement, so it cannot race itself here.
        """
        self._acquire()
        try:
            self._identity(session, generation)
            w = self.words
            if w[_STATE] != INSTALLED:
                return ()
            return tuple(
                slot for slot, o in enumerate((_SLOT0, _SLOT1)) if w[o] == w[o + 1]
            )
        finally:
            self.lock.release()

    def pending(self, session, generation):
        """Return both pending descriptors in order, including ones being retired.

        Observing is NOT releasing: repeated polls may return the same sequence.
        The native broker deduplicates identity and retains only its latest lease.
        """
        self._acquire()
        try:
            self._identity(session, generation)
            w = self.words
            if w[_STATE] not in (INSTALLED, RETIRING):
                return ()
            frames = [
                TextureFrame(session, generation, slot, w[o], w[o + 2], w[o + 3])
                for slot, o in enumerate((_SLOT0, _SLOT1))
                if w[o] > w[o + 1]
            ]
            return tuple(sorted(frames, key=lambda frame: frame.sequence))
        finally:
            self.lock.release()

    def release(self, frame):
        """GUI calls after the LAST native lease has returned GPU key 0."""
        _integer(frame.slot, 0, 1, "slot")
        _integer(frame.sequence, 1, MAX_INTEGER, "sequence")
        self._acquire()
        try:
            self._identity(frame.session, frame.generation)
            w = self.words
            offset = (_SLOT0, _SLOT1)[frame.slot]
            if w[_STATE] not in (INSTALLED, RETIRING):
                raise RuntimeError("Texture pool cannot release frames")
            if w[offset] != frame.sequence or w[offset + 1] == frame.sequence:
                raise ValueError("Stale or duplicate texture release")
            w[offset + 1] = frame.sequence
        finally:
            self.lock.release()

    def retire(self, session, generation):
        """Producer stops publishing; GUI must drop broker leases before ack."""
        self._acquire()
        try:
            self._identity(session, generation)
            if self.words[_STATE] not in (OFFERED, INSTALLED, RETIRING):
                raise RuntimeError("Texture pool cannot retire")
            self.words[_STATE] = RETIRING
        finally:
            self.lock.release()

        self.notify()

    def finish_retirement(self, session, generation):
        """GUI acknowledges after import cancellation and all native releases."""
        self._acquire()
        try:
            self._identity(session, generation)
            w = self.words
            if w[_STATE] != RETIRING:
                raise RuntimeError("Texture pool is not retiring")
            if any(w[o] != w[o + 1] for o in (_SLOT0, _SLOT1)):
                raise RuntimeError("Texture pool still has native leases")
            w[_STATE] = RETIRED
        finally:
            self.lock.release()

    def state(self):
        self._acquire()
        try:
            return self.words[_STATE]
        finally:
            self.lock.release()

    def close(self):
        """Terminal metadata invalidation, NOT a resource-release acknowledgement.

        The caller must invalidate native consumers and stop the owned worker.
        A new session gets a new mailbox; CLOSED cannot be reopened.
        """
        self._acquire()
        try:
            self.words[_STATE] = CLOSED
        finally:
            self.lock.release()
        self.notify()
