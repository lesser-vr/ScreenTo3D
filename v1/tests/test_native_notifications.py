"""Qt controller regression: render requests follow broker publication, not stats."""
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject
from screento3d_app import live_preview
from screento3d_app.capture_mailbox import ACK, HEIGHT, RECEIVED, RUNNING, SEQ, STATE, WIDTH


class NativeNotifications(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.desktop = QObject()
        self.desktop.preferences = SimpleNamespace(selection=lambda *_: dict(
            mode='performance', model='da2-small', stereo_layout='half-tb'))
        with patch.object(live_preview, 'windows', return_value=[]):
            self.live = live_preview.LivePreview(self.desktop)
        live = self.live
        live.process = Mock()
        live.process.is_alive.return_value = True
        live.last_health = live.last_stats = time.perf_counter()
        live.native_selected = True
        live.native = SimpleNamespace(consume=Mock(return_value=False), has_frame=True)
        meta = [0] * 12
        meta[WIDTH], meta[HEIGHT], meta[STATE], meta[RECEIVED] = 640, 180, RUNNING, 1
        live.mailbox = SimpleNamespace(meta=meta, lock=threading.Lock())
        self.notifications = []
        live.frameChanged.connect(lambda: self.notifications.append((live.frameRevision, live.hasFrame)))
        live.abort = Mock(side_effect=AssertionError)

    def tearDown(self):
        self.live.process = None

    def test_metadata_before_delayed_publication_does_not_lose_wakeup(self):
        live = self.live
        live.mailbox.meta[SEQ] = 1
        live.poll()  # Cap holds the texture, while worker stats arrive now.
        self.assertEqual(live.mailbox.meta[ACK], 1)
        self.assertEqual(self.notifications, [])
        live.native.consume.return_value = True
        live.poll()  # Real publication, with no new worker statistics.
        self.assertEqual(self.notifications, [(1, True)])
        live.native.consume.return_value = False
        live.poll()
        self.assertEqual(len(self.notifications), 1)

    def test_publication_before_metadata_does_not_trigger_duplicate_render(self):
        live = self.live
        live.native.consume.return_value = True
        live.poll()
        live.native.consume.return_value = False
        live.mailbox.meta[SEQ] = 1
        live.poll()
        self.assertEqual(self.notifications, [(1, True)])

    def test_timed_publication_and_retirement_each_wake_surface(self):
        live = self.live
        live.vfg_enabled = True
        live.native.consume.return_value = True
        live.poll()
        live.native.has_frame = False
        live.poll()
        self.assertEqual(self.notifications, [(1, True), (2, False)])


if __name__ == '__main__':
    unittest.main()
