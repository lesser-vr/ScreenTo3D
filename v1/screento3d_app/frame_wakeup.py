"""Bounded metadata wakeups using a local socket pair; no capture or GPU access."""

from .messages import Message as M
import socket

from PySide6.QtCore import QObject, QSocketNotifier, Signal


class FrameWakeup(QObject):
    ready = Signal()
    failed = Signal(object)
    health_interval_ms = 50
    event_driven = True

    def __init__(self, parent=None):
        super().__init__(parent)
        self.reader, self.writer = socket.socketpair()
        # Windows socketpair uses loopback TCP. These one-byte wakeups must not
        # wait for packet coalescing; pixels and descriptors never enter here.
        if self.writer.family in (socket.AF_INET, socket.AF_INET6):
            self.writer.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.reader.setblocking(False)
        self.writer.setblocking(False)
        self.closed = False
        self.wakeups = 0
        self.notifier = QSocketNotifier(self.reader.fileno(), QSocketNotifier.Type.Read, self)
        self.notifier.activated.connect(self._ready)

    def _ready(self, *args):
        if self.closed:
            return
        try:
            data = self.reader.recv(4096)
            if not data:
                raise ConnectionError('Frame notification channel closed')
        except BlockingIOError:
            return
        except OSError:
            self.notifier.setEnabled(False)
            self.failed.emit(M('The frame-ready notification connection closed.'))
            return
        self.wakeups += 1
        self.ready.emit()

    def close(self):
        if not self.closed:
            self.closed = True
            self.notifier.setEnabled(False)
            self.writer.close()
            self.reader.close()
