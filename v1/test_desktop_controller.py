"""Qt controller regression without model loading."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QProcess, QUrl, QSettings
from PySide6.QtWidgets import QApplication, QMessageBox
from depthsbs_app.desktop import DesktopController
from depthsbs_app.desktop_preferences import DesktopPreferences

APP = QApplication.instance() or QApplication([])


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "한글 & input.mp4"
        self.source.touch()
        self.c = DesktopController(DesktopPreferences(QSettings(str(self.root/'preferences.ini'), QSettings.IniFormat)))
        self.c.add_paths([str(self.source)])

    def test_duplicate_and_remote_drop(self):
        self.c.dropFiles(
            [
                QUrl.fromLocalFile(str(self.source)),
                QUrl("https://example.com/video.mp4"),
            ]
        )
        self.assertEqual(len(self.c.rows), 1)

    def test_bounded_queue(self):
        paths = []
        for i in range(40):
            p = self.root / f"{i}.mp4"
            p.touch()
            paths.append(str(p))
        self.c.add_paths(paths)
        self.assertEqual(len(self.c.rows), 32)

    def test_settings_and_selection_locked(self):
        original = self.c.settings["mode"]
        self.c.lease.acquire("live")
        self.c.setOption("mode", "balanced")
        self.c.removeSelected()
        self.assertEqual(self.c.settings["mode"], original)
        self.assertEqual(len(self.c.rows), 1)

    def test_offline_mode_selects_dedicated_vda_label(self):
        self.c.setOption("mode", "offline-quality")
        self.assertEqual(self.c.settings["model"], "vda-small")
        self.assertEqual(
            self.c.models,
            [{"key": "vda-small", "label": "VDA Small · 5-frame Offline"}],
        )

    def test_license_reset_on_model_change(self):
        self.c.setOption("mode", "video-quality")
        self.c.setOption("model", "ovda-small-c16")
        self.c.setOption("noncommercial", True)
        self.c.setOption("model", "vda-small")
        self.assertFalse(self.c.settings["noncommercial"])

    def test_model_paths_do_not_leak_across_selection(self):
        self.c.setOption("mode", "video-quality")
        self.c.setOption("model", "vda-small")
        self.c.setOption("engine", str(self.root))
        self.c.setOption("model", "ovda-small-c16")
        self.assertNotEqual(self.c.settings["engine"], str(self.root))
        self.c.setOption("model", "vda-small")
        self.assertEqual(self.c.settings["engine"], str(self.root))

    def _fake_active(self):
        self.c.active = self.c.snapshot()
        self.c.lease.acquire("file")
        self.c.process = QProcess(self.c)

    def test_no_false_success_without_complete(self):
        self._fake_active()
        Path(self.c.destination).touch()
        self.c._finished(0, QProcess.NormalExit)
        self.assertFalse(self.c.canOpen)
        self.assertEqual(self.c.rows[0]["state"], "failed")

    def test_complete_then_crash_is_error(self):
        self._fake_active()
        Path(self.c.destination).touch()
        self.c._event({"event": "complete"})
        self.c._finished(1, QProcess.CrashExit)
        self.assertFalse(self.c.canOpen)

    def test_complete_and_exit_enables_open(self):
        self._fake_active()
        Path(self.c.destination).touch()
        self.c._event({"event": "complete"})
        self.c._finished(0, QProcess.NormalExit)
        self.assertTrue(self.c.canOpen)

    def test_failed_start_releases_lease(self):
        self._fake_active()
        self.c._process_error(QProcess.FailedToStart)
        self.assertFalse(self.c.busy)
        self.assertIn("Cannot start", self.c.status)

    def test_cancel_error_is_not_successful_cancel(self):
        self._fake_active()
        self.c._event({"event": "error", "message": "cleanup failed"})
        self.c._finished(2, QProcess.NormalExit)
        self.assertEqual(self.c.rows[0]["state"], "failed")

    def test_malformed_translation_keeps_original_failure(self):
        self._fake_active()
        self.c._event(dict(event='error',message='opaque failure CODE-42',
                           localized=dict(source='{value:1000000000}',values=dict(value='invalid'))))
        self.c._finished(1,QProcess.CrashExit)
        self.assertIn('opaque failure CODE-42',self.c.status)
        self.assertEqual(self.c.rows[0]['state'],'failed')

    def test_close_waits_for_cleanup(self):
        self._fake_active()
        self.c.cancel_path = self.root / "cancel"
        with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            self.assertFalse(self.c.requestClose())
        self.assertTrue(self.c.cancel_path.exists())
        exits = []
        self.c.exitReady.connect(lambda: exits.append(True))
        self.assertTrue(self.c.busy)
        self.c._finished(2, QProcess.NormalExit)
        self.assertEqual(exits, [True])

    def test_close_declined_preserves_work(self):
        self._fake_active()
        with patch.object(QMessageBox, "question", return_value=QMessageBox.No):
            self.assertFalse(self.c.requestClose())
        self.assertFalse(self.c.closing)
        self.c._finished(2, QProcess.NormalExit)


if __name__ == "__main__":
    unittest.main()
