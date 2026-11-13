"""Bounded local notifications and GUI wakeups; no captured pixels or GPU work."""
import multiprocessing as mp
import unittest

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEventLoop, QTimer

from screento3d_app.frame_wakeup import FrameWakeup
from screento3d_app.texture_mailbox import TextureMailbox


class FrameWakeupTests(unittest.TestCase):
    def wait_until(self, predicate):
        loop = QEventLoop()
        check = QTimer()
        check.timeout.connect(lambda: loop.quit() if predicate() else None)
        timeout = QTimer()
        timeout.setSingleShot(True)
        timeout.timeout.connect(loop.quit)
        check.start(1)
        timeout.start(1000)
        loop.exec()
        self.assertTrue(predicate())

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_coalescing_and_notification_during_callback_do_not_lose_wakeups(self):
        wake = FrameWakeup()
        box = TextureMailbox.create(mp.get_context('spawn'))
        box.wake_writer = wake.writer
        calls = []
        def ready():
            calls.append(1)
            if len(calls) == 1:
                box.notify()
        wake.ready.connect(ready)
        try:
            for _ in range(50):
                box.notify()
            self.wait_until(lambda: len(calls) >= 2)
            self.assertEqual(len(calls), 2)
        finally:
            wake.close()
            self.assertEqual(wake.reader.fileno(), -1)
            self.assertEqual(wake.writer.fileno(), -1)
            wake.deleteLater()

    def test_full_channel_is_bounded_and_already_readable(self):
        wake = FrameWakeup()
        box = TextureMailbox.create(mp.get_context('spawn'))
        box.wake_writer = wake.writer
        calls = []
        wake.ready.connect(lambda: calls.append(1))
        try:
            # Fill without GUI service; a failed nonblocking write is safe because
            # unread bytes already guarantee a wakeup. No per-frame queue grows.
            while True:
                try:
                    wake.writer.send(b'x' * 65536)
                except BlockingIOError:
                    break
            box.notify()
            self.wait_until(lambda: bool(calls))
        finally:
            wake.close()
            wake.deleteLater()

    def test_closed_peer_reports_failure_and_disables_notifier(self):
        wake = FrameWakeup()
        errors = []
        wake.failed.connect(errors.append)
        try:
            wake.writer.close()
            self.wait_until(lambda: bool(errors))
            self.assertEqual(len(errors), 1)
            self.assertFalse(wake.notifier.isEnabled())
        finally:
            wake.close()
            wake.close()
            wake.deleteLater()
