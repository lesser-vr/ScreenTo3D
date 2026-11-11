"""Qt controller regression without model loading."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,Mock

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
        self.c.shutdown.command=Mock(side_effect=AssertionError('Real shutdown is forbidden in tests'))
        self.addCleanup(self.c.shutdown.cancel)
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

    def _start_queue(self):
        source=self.root/'second.mp4';source.touch();self.c.add_paths([str(source)])
        def spawn(*ignored):self.c.process=QProcess(self.c)
        with patch('depthsbs_app.desktop.Job.validate'),patch.object(self.c.downloads,'needed',return_value=False),patch.object(self.c,'_spawn',side_effect=spawn):
            self.c.start()
        return source

    def _finish_success(self):
        Path(self.c.active.output).touch();self.c._event({'event':'complete'})
        def spawn(*ignored):self.c.process=QProcess(self.c)
        with patch('depthsbs_app.desktop.Job.validate'),patch.object(self.c,'_spawn',side_effect=spawn):
            self.c._finished(0,QProcess.NormalExit)

    def test_queue_continues_in_order_with_one_lease_and_frozen_settings(self):
        self._start_queue();first=self.c.active
        with patch.object(self.c.lease,'release',wraps=self.c.lease.release) as release:
            self._finish_success();release.assert_not_called()
        self.assertEqual([r['state'] for r in self.c.rows],['completed','running'])
        self.assertEqual(self.c.selected,1);self.assertEqual(self.c.lease.owner,'file')
        self.assertEqual(self.c.active.model,first.model);self.assertEqual(self.c.active.stereo_layout,first.stereo_layout)
        self.c.setOption('mode','performance');self.assertEqual(self.c.active.model,self.c.values['model'])
        self._finish_success()
        self.assertTrue(all(r['state']=='completed' for r in self.c.rows));self.assertFalse(self.c.busy)
        self.assertFalse(self.c.shutdown.pending)

    def test_failure_stops_queue_and_disarms_shutdown(self):
        self.c.shutdown.setSelected(True);self._start_queue()
        self.c._finished(1,QProcess.NormalExit)
        self.assertEqual([r['state'] for r in self.c.rows],['failed','queued'])
        self.assertFalse(self.c.busy);self.assertFalse(self.c.shutdown.selected)

    def test_explicit_cancel_does_not_continue_even_if_current_file_succeeds(self):
        self.c.shutdown.setSelected(True);self._start_queue();self.c.cancel();self._finish_success()
        self.assertEqual([r['state'] for r in self.c.rows],['completed','queued'])
        self.assertFalse(self.c.shutdown.pending);self.assertFalse(self.c.busy)

    def test_only_whole_successful_queue_arms_shutdown(self):
        self.c.shutdown.setSelected(True);self._start_queue();self._finish_success()
        self.assertFalse(self.c.shutdown.pending);self._finish_success()
        self.assertTrue(self.c.shutdown.pending);self.assertEqual(self.c.lease.owner,'shutdown')
        self.c.shutdown.command.assert_not_called()
        self.assertTrue(self.c.requestClose());self.assertFalse(self.c.shutdown.pending)

    def test_late_output_collision_stops_and_preserves_new_file(self):
        self.c.shutdown.setSelected(True);self._start_queue()
        output=Path(self.c.rows[1]['output']);output.write_bytes(b'new unrelated file')
        self._finish_success()
        self.assertEqual(output.read_bytes(),b'new unrelated file')
        self.assertEqual(self.c.rows[1]['state'],'failed');self.assertFalse(self.c.busy)
        self.assertFalse(self.c.shutdown.pending)

    def test_output_format_renames_only_automatic_pending_paths(self):
        original=self.c.destination
        self.assertTrue(original.endswith('_Half_TB.mp4'))
        self.c.setOption('stereo_layout','full-sbs')
        self.assertTrue(self.c.destination.endswith('_Full_SBS.mp4'))
        custom=str(self.root/'custom.mp4')
        with patch('depthsbs_app.desktop.QFileDialog.getSaveFileName',return_value=(custom,'')):
            self.c.chooseOutput()
        self.c.setOption('stereo_layout','half-sbs');self.assertEqual(self.c.destination,custom)

    def test_completed_output_path_survives_format_changes(self):
        self.c.rows[0]['state']='completed';original=self.c.destination
        self.c.setOption('stereo_layout','full-sbs');self.assertEqual(self.c.destination,original)


if __name__ == "__main__":
    unittest.main()
