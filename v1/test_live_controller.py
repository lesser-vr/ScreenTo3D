"""No-capture controller tests for leases, stop/privacy and malformed sources."""

import multiprocessing as mp
import time
import unittest
from unittest.mock import Mock, patch
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage
from depthsbs_app.desktop import DesktopController
from depthsbs_app.live_preview import LivePreview
from depthsbs_app.capture_mailbox import Mailbox

APP = QApplication.instance() or QApplication([])


class LiveControllerTests(unittest.TestCase):
    def setUp(self):
        self.desktop = DesktopController()
        self.live = LivePreview(self.desktop)
        # Existing controller cases explicitly exercise the host diagnostic path.
        self.live.setProcessingPath("gpu")
        self.desktop.live = self.live
        # Tests exercise an explicitly selected synthetic source, never the
        # user's first enumerated window. Initial selection is now empty.
        self.live.items = [dict(kind="window", id=11, pid=1, label="Fixture")]
        self.live.selected = 0
        self.live.output_placement.save = Mock()

    def test_file_work_prevents_capture(self):
        self.desktop.lease.acquire("file")
        self.live.start()
        self.assertFalse(self.live.active)
        self.assertEqual(self.desktop.lease.owner, "file")

    def test_initial_refresh_never_selects_a_window(self):
        with patch("depthsbs_app.live_preview.windows", return_value=[dict(kind="window", id=11, pid=1, label="A")]):
            live = LivePreview(self.desktop)
            live.refresh()
            self.assertEqual(live.selectedIndex, -1)
            self.assertFalse(live.active)

    def test_close_live_app_stops_without_confirmation_and_keeps_lease(self):
        self.fake_active()
        with patch("depthsbs_app.desktop.QMessageBox.question") as question:
            self.assertFalse(self.desktop.requestClose())
            question.assert_not_called()
        self.assertTrue(self.desktop.closing)
        self.assertTrue(self.live.stopping)
        self.assertTrue(self.desktop.busy)
        self.live.process.is_alive.return_value = False
        exited = Mock()
        self.desktop.exitReady.connect(exited)
        self.live.poll()
        exited.assert_called_once()
        self.assertFalse(self.desktop.busy)

    def test_refresh_preserves_identity_and_requires_selection_after_loss(self):
        a = dict(kind="window", id=11, pid=1, label="A")
        b = dict(kind="window", id=22, pid=2, label="B")
        self.live.items, self.live.selected = [a, b], 1
        renamed = dict(b, label="Changed title")
        with patch("depthsbs_app.live_preview.windows", return_value=[renamed, a]):
            self.live.refresh()
        self.assertEqual(self.live.selectedIndex, 0)
        self.assertEqual(self.live.items[0]["label"], "Changed title")
        # Reused HWND in another process is not the same source.
        with patch("depthsbs_app.live_preview.windows", return_value=[dict(b, pid=9), a]):
            self.live.refresh()
            self.assertEqual(self.live.selectedIndex, -1)
            self.live.refresh()
            self.assertEqual(self.live.selectedIndex, -1)
        self.assertIn("다시 선택", self.live.status)
        self.live.select(1)
        self.assertFalse(self.live.selection_required)

    def test_refresh_preserves_monitor_device_when_enumeration_changes(self):
        self.live.kind = "monitor"
        self.live.items = [dict(kind="monitor", id=1, device="DISPLAY_A", label="A")]
        self.live.selected = 0
        with patch("depthsbs_app.live_preview.monitors", return_value=[
            dict(kind="monitor", id=1, device="DISPLAY_B", label="B"),
            dict(kind="monitor", id=2, device="DISPLAY_A", label="A"),
        ]):
            self.live.refresh()
        self.assertEqual(self.live.selectedIndex, 1)

    def test_setup_check_uses_explicit_target_without_changing_file_options(self):
        self.live.setMode("performance")
        original = dict(self.desktop.values)
        with patch.object(self.desktop, "_spawn") as spawn:
            self.desktop.checkSetupFor("live")
            args = spawn.call_args.args[1]
            self.assertEqual(args[0], "da2-small")
            self.assertIn("실시간 SBS", self.desktop.setup)
            self.assertEqual(self.desktop.values, original)
        self.desktop._cleanup()
        with patch.object(self.desktop, "_spawn") as spawn:
            self.desktop.checkSetupFor("file")
            self.assertEqual(spawn.call_args.args[1][0], original["model"])
            self.assertIn("파일 변환", self.desktop.setup)
        self.desktop._cleanup()

    def test_local_gui_defaults_to_native_without_loading_it(self):
        with patch("depthsbs_app.live_preview.os.environ", {}):
            live = LivePreview(self.desktop)
        self.assertEqual(live.processingPath, "gpu-texture")
        self.assertFalse(live.nativeReady)
        self.assertFalse(live.hasFrame)
        self.assertIsNone(live.report()['native_delivery'])
        self.assertEqual(live.presentationHz, 0)
        from depthsbs_app.live_policy import LIVE_MODES
        self.assertTrue(all(policy.presentation_hz == 0 for policy in LIVE_MODES.values()))

    def test_default_native_failure_releases_lease_without_fallback(self):
        with patch("depthsbs_app.live_preview.os.environ", {}):
            live = LivePreview(self.desktop)
        live.items = [dict(kind='window', id=11, pid=1, width=640, height=360)]
        live.selected = 0
        with patch('depthsbs_app.live_preview.validate_source'), patch(
            'depthsbs_app.native_delivery.NativeDelivery', side_effect=RuntimeError('hash mismatch')
        ), patch('depthsbs_app.live_preview.mp.get_context') as context:
            live.start()
        self.assertEqual(live.processingPath, 'gpu-texture')
        self.assertIsNone(self.desktop.lease.owner)
        self.assertFalse(live.active)
        self.assertFalse(live.nativeReady)
        self.assertIn('hash mismatch', live.status)
        self.assertIn('GPU 호스트 출력', live.status)
        context.return_value.Process.assert_not_called()
        live.setProcessingPath('gpu')
        self.assertEqual(live.processingPath, 'gpu')

    def test_model_owned_mode_selection(self):
        self.assertEqual(self.live.liveMode, "balanced")
        self.assertEqual(self.live.liveModel, "da2-base")
        self.assertTrue(self.live.sbsEnabled)
        self.live.setSbs(True)
        self.assertEqual(self.live.report()["plan"]["model"], "da2-base")
        self.assertEqual(
            self.live.report()["plan"]["stereo"]["depth_backend"], "da2-base"
        )
        self.live.setMode("performance")
        self.assertEqual(self.live.liveModel, "da2-small")
        self.live.setMode("video-quality")
        self.assertEqual(self.live.liveModel, "vda-small")
        self.live.setLiveModel("ovda-small-c16")
        self.assertEqual(self.live.liveModel, "ovda-small-c16")

    def test_user_start_rejects_invalid_output_without_capture(self):
        with patch.object(self.live, "start") as start:
            self.live.startSbs(9, 0)
            self.live.startSbs(0, -1)
            start.assert_not_called()
        self.assertFalse(self.live.active)

    def test_user_start_forces_sbs_without_changing_model(self):
        self.live.setSbs(False)
        self.live.items = [dict(label="Test source")]
        self.live.selected = 0
        with patch.object(self.live, "start") as start:
            self.live.startSbs(2, -1)
            start.assert_called_once()
        self.assertTrue(self.live.sbsEnabled)
        self.assertEqual(self.live.liveModel, "da2-base")

    def test_user_start_does_not_change_busy_diagnostic(self):
        self.live.setSbs(False)
        self.desktop.lease.acquire("file")
        with patch.object(self.live, "start") as start:
            self.live.startSbs(2, -1)
            start.assert_not_called()
        self.assertFalse(self.live.sbsEnabled)
        self.assertIn("다른 작업", self.live.status)

    def test_user_start_explains_missing_or_stale_selection(self):
        self.live.items = []
        for index in (-1, 0, 5):
            self.live.selected = index
            with patch.object(self.live, "start") as start:
                self.live.startSbs(2, -1)
                start.assert_not_called()
            self.assertIn("볼 창을 선택", self.live.status)

    def test_user_start_output_failure_stops_owned_worker(self):
        self.live.output_window = Mock()
        self.live.output_window.isVisible.return_value = False
        with patch.object(self.live, "start", side_effect=self.fake_active), patch.object(
            self.live, "showOutput"
        ) as show:
            self.live.startSbs(0, 0)
            show.assert_called_once_with(0, False)
        self.assertTrue(self.live.stopping)
        self.assertTrue(self.desktop.busy)
        self.assertIn("출력 창", self.live.status)
        self.live.process.is_alive.return_value = False
        self.live.poll()
        self.assertFalse(self.desktop.busy)

    def test_failed_start_never_opens_output(self):
        with patch.object(self.live, "start"), patch.object(self.live, "showOutput") as show:
            self.live.startSbs(1, 0)
            show.assert_not_called()

    def test_output_exception_stops_owned_worker(self):
        with patch.object(self.live, "start", side_effect=self.fake_active), patch.object(
            self.live, "showOutput", side_effect=RuntimeError("display lost")
        ):
            self.live.startSbs(0, 0)
        self.assertTrue(self.live.stopping)
        self.assertIn("display lost", self.live.status)
        self.assertTrue(self.desktop.busy)
        self.live.process.is_alive.return_value = False
        self.live.poll()
        self.assertFalse(self.desktop.busy)

    def test_user_start_requests_fullscreen_explicitly(self):
        self.live.output_window = Mock()
        self.live.output_window.isVisible.return_value = True
        with patch.object(self.live, "start", side_effect=self.fake_active), patch.object(
            self.live, "showOutput"
        ) as show:
            self.live.startSbs(1, 0)
            show.assert_called_once_with(0, True)
        self.live.stop()
        self.live.process.is_alive.return_value = False
        self.live.poll()

    def test_file_mode_selection_updates_owned_model(self):
        self.assertEqual(self.desktop.settings["model"], "da2-base")
        self.desktop.setOption("mode", "performance")
        self.assertEqual(self.desktop.settings["model"], "da2-small")
        self.desktop.setOption("mode", "video-quality")
        self.assertEqual(self.desktop.settings["model"], "vda-small")
        self.desktop.setOption("model", "ovda-small-c16")
        self.assertEqual(self.desktop.settings["model"], "ovda-small-c16")
        self.desktop.setOption("model", "da2-small")
        self.assertEqual(self.desktop.settings["model"], "ovda-small-c16")

    def test_explicit_reference_environment_remains_available(self):
        with patch(
            "depthsbs_app.live_preview.os.environ", {"DEPTHSBS_LIVE_GPU_CANDIDATE": "0"}
        ):
            live = LivePreview(self.desktop)
        self.assertEqual(live.processingPath, "reference")

    def test_native_is_explicit_and_locked_while_active(self):
        self.live.setSbs(True)
        self.live.setMode("performance")
        with patch("depthsbs_app.native_delivery.NativeDelivery"):
            self.live.setProcessingPath("gpu-texture")
        self.assertTrue(self.live.nativeEnabled)
        self.assertTrue(self.live.gpu_candidate)
        self.fake_active()
        self.live.setProcessingPath("gpu")
        self.assertEqual(self.live.processingPath, "gpu-texture")
        self.live.stop()
        self.live.native.end.assert_called_once()

    def test_native_supports_device_depth_video_models(self):
        self.live.setSbs(True)
        self.live.setMode("video-quality")
        self.assertEqual(self.live.liveModel, "vda-small")
        self.assertTrue(self.live.nativeCapable)
        with patch("depthsbs_app.native_delivery.NativeDelivery"):
            self.live.setProcessingPath("gpu-texture")
        self.assertTrue(self.live.nativeEnabled)
        self.live.setLiveModel("ovda-small-c16")
        self.assertTrue(self.live.nativeEnabled)

    def test_base_uses_source_device_depth_and_supports_explicit_native(self):
        self.live.setSbs(True)
        self.assertEqual(self.live.liveModel, "da2-base")
        self.assertEqual(self.live.report()["processing_path"], "model-device-depth-gpu-stereo-host-output")
        with patch("depthsbs_app.native_delivery.NativeDelivery"):
            self.live.setProcessingPath("gpu-texture")
        self.assertTrue(self.live.nativeEnabled)
        self.assertEqual(self.live.report()["processing_path"], "gpu-texture")
        self.live.setProcessingPath("reference")
        self.assertEqual(self.live.report()["processing_path"], "model-host-depth-cuda-stereo")

    def test_native_load_failure_does_not_select_or_start_it(self):
        self.live.setMode("performance")
        with patch(
            "depthsbs_app.native_delivery.NativeDelivery",
            side_effect=RuntimeError("hash mismatch"),
        ):
            self.live.setProcessingPath("gpu-texture")
        self.assertFalse(self.live.nativeEnabled)
        self.assertFalse(self.live.active)
        self.assertIn("hash mismatch", self.live.status)

    def test_processing_and_cadence_snapshot_controls(self):
        self.live.setProcessingPath("gpu")
        self.live.setPresentationHz(30)
        self.assertEqual(self.live.presentationHz, 30)
        self.live.setPresentationHz(0)
        self.assertEqual(self.live.presentationHz, 0)
        self.live.setPresentationHz(60)
        self.assertEqual(self.live.processingPath, "gpu")
        self.assertEqual(self.live.presentationHz, 60)
        self.fake_active()
        self.live.setProcessingPath("reference")
        self.live.setPresentationHz(30)
        self.live.setPresentationHz(0)
        self.assertEqual(self.live.processingPath, "gpu")
        self.assertEqual(self.live.presentationHz, 60)
        self.live.stop()

    def test_bad_source_does_not_take_lease(self):
        self.live.items = [dict(kind="window", id=0, pid=0, width=100, height=100)]
        self.live.selected = 0
        self.live.start()
        self.assertFalse(self.desktop.busy)
        self.assertFalse(self.live.active)

    def fake_active(self):
        self.desktop.lease.acquire("live")
        self.live.process = Mock()
        self.live.process.is_alive.return_value = True
        self.live.process.exitcode = 0
        self.live.mailbox = Mailbox.create(mp.get_context("spawn"))
        self.live.provider.image = QImage(16, 16, QImage.Format_RGB32)
        self.live.started = time.perf_counter()

    def test_stop_clears_frame_before_worker_exit(self):
        self.fake_active()
        self.live.copy_pool.copy(self.live.mailbox.pixels, 16, 16)
        self.live.stop()
        self.assertTrue(self.live.mailbox.stop.is_set())
        self.assertTrue(self.live.provider.image.isNull())
        self.assertTrue(self.desktop.busy)
        self.assertEqual(self.live.copy_pool.images, [])

    def test_copy_pool_preserves_retained_readers_and_resize(self):
        import numpy as np
        from depthsbs_app.owned_preview_image import PreviewCopyPool

        pool = PreviewCopyPool()
        pixels = np.zeros(32 * 32 * 4, np.uint8)
        readers = []
        for value in range(8):
            pixels[:] = value
            readers.append(pool.copy(pixels, 16, 16))
            self.assertEqual(len(pool.images), 2)
        for value, reader in enumerate(readers):
            self.assertTrue(
                np.all(np.frombuffer(reader.constBits(), np.uint8) == value)
            )
        pixels[:] = 99
        resized = pool.copy(pixels, 32, 32)
        self.assertEqual(resized.width(), 32)
        pool.clear()
        self.assertEqual(pool.images, [])
        self.assertEqual(readers[0].pixelColor(0, 0).blue(), 0)
        self.assertEqual(resized.pixelColor(0, 0).blue(), 99)

    def test_frame_notification_can_run_after_mailbox_unlock(self):
        from depthsbs_app.capture_mailbox import SEQ, WIDTH, HEIGHT, RUNNING, STATE

        self.fake_active()
        self.live.notify_unlocked = True
        self.live.last_health = self.live.last_stats = time.perf_counter()
        box = self.live.mailbox
        box.meta[SEQ], box.meta[WIDTH], box.meta[HEIGHT], box.meta[STATE] = (
            1,
            16,
            16,
            RUNNING,
        )
        box.pixels[0] = 71
        observed = []

        def inspect_frame():
            acquired = box.lock.acquire(False)
            observed.append(acquired)
            if acquired:
                box.pixels[0] = 99
                box.lock.release()

        self.live.frameChanged.connect(inspect_frame)
        self.live.poll()
        self.assertEqual(observed, [True])
        self.assertEqual(self.live.provider.image.pixelColor(0, 0).blue(), 71)
        self.assertEqual(self.live.submitted, 1)

    def test_copy_failure_stops_without_acknowledging_partial_frame(self):
        from depthsbs_app.capture_mailbox import SEQ, ACK, WIDTH, HEIGHT, RUNNING, STATE

        self.fake_active()
        self.live.use_copy_pool = True
        self.live.last_health = self.live.last_stats = time.perf_counter()
        box = self.live.mailbox
        box.meta[SEQ], box.meta[WIDTH], box.meta[HEIGHT], box.meta[STATE] = (
            1,
            16,
            16,
            RUNNING,
        )
        with patch.object(
            self.live.copy_pool, "copy", side_effect=RuntimeError("copy failed")
        ):
            self.live.poll()
        self.assertTrue(self.live.stopping)
        self.assertTrue(self.live.provider.image.isNull())
        self.assertEqual(box.meta[ACK], 0)
        self.assertIn("copy failed", self.live.status)

    def test_only_cleanup_releases_lease(self):
        self.fake_active()
        self.live.stop()
        self.live.process.is_alive.return_value = False
        self.live.poll()
        self.assertFalse(self.desktop.busy)
        self.assertFalse(self.live.active)

    def test_crash_clears_frame_and_releases(self):
        self.fake_active()
        self.live.process.is_alive.return_value = False
        self.live.process.exitcode = 99
        self.live.poll()
        self.assertFalse(self.desktop.busy)
        self.assertTrue(self.live.provider.image.isNull())
        self.assertIn("99", self.live.status)

    def test_hidden_page_never_counts_swaps(self):
        self.fake_active()
        self.live.pending_present = (time.perf_counter_ns(), 0)
        self.live.setPreviewVisible(False)
        self.live.frameSwapped()
        self.assertEqual(self.live.presented, 0)

    def test_metrics_are_bounded(self):
        self.fake_active()
        for _ in range(1000):
            self.live.pending_present = (time.perf_counter_ns(), time.perf_counter_ns())
            self.live.frameSwapped()
        self.assertEqual(len(self.live.latencies), 512)

    def test_source_and_cursor_locked_during_capture(self):
        self.fake_active()
        self.live.setKind("monitor")
        self.live.setCursor(False)
        self.assertEqual(self.live.sourceKind, "window")
        self.assertTrue(self.live.cursorIncluded)

    def test_timeout_terminates_only_capture_worker(self):
        self.fake_active()
        self.live.stop()
        self.live.stop_started -= 6
        worker = self.live.process
        self.live.poll()
        worker.terminate.assert_called_once()
        self.assertTrue(self.desktop.busy)

    def test_live_settings_snapshot(self):
        self.live.setSbs(True)
        self.live.setMode("performance")
        self.live.setStrength(1.5)
        self.fake_active()
        self.live.setSbs(False)
        self.live.setMode("video-quality")
        self.live.setStrength(0.25)
        self.assertTrue(self.live.sbsEnabled)
        self.assertEqual(self.live.liveMode, "performance")
        self.assertEqual(self.live.depthStrength, 1.5)

    def test_offline_mode_rejected(self):
        self.live.setMode("offline-quality")
        self.assertEqual(self.live.liveMode, "balanced")
        self.assertIn("파일 전용", self.live.status)

    def test_output_exclusion_failure_does_not_show(self):
        self.live.output_window = Mock()
        with patch("depthsbs_app.capture_sources.exclude_preview", return_value=False):
            self.live.showOutput(0, True)
        self.live.output_window.showFullScreen.assert_not_called()
        self.assertFalse(self.live.output_excluded)

    def test_start_failure_emits_error_without_worker(self):
        errors = []
        self.live.errorOccurred.connect(errors.append)
        self.live.items = [dict(label='Fixture')]
        self.live.selected = 0
        with patch('depthsbs_app.live_preview.validate_source', side_effect=ValueError('Rejected source')):
            self.live.startSbs(2, -1)
        self.assertEqual(errors, ['Rejected source'])
        self.assertFalse(self.live.active)

    def test_worker_failure_notifies_once_after_cleanup(self):
        errors = []
        self.live.errorOccurred.connect(lambda message: errors.append((message, self.desktop.busy)))
        self.fake_active()
        self.live.mailbox.error.value = b'Worker failed'
        self.live.process.is_alive.return_value = False
        self.live.poll()
        self.live.poll()
        self.assertEqual(errors, [('Worker failed', False)])

    def test_normal_stop_does_not_show_error(self):
        errors = []
        self.live.errorOccurred.connect(errors.append)
        self.fake_active()
        self.live.stop()
        self.live.process.is_alive.return_value = False
        self.live.poll()
        self.assertEqual(errors, [])

    def test_reopen_failure_reports_and_stops(self):
        errors = []
        self.live.errorOccurred.connect(errors.append)
        self.fake_active()
        self.live.output_window = Mock()
        with patch.object(self.live, 'showOutput', side_effect=ValueError('Unsafe output')):
            self.live.requestOutput(0, True)
        self.assertTrue(self.live.stopping)
        self.assertEqual(errors, ['Unsafe output'])

    def test_screen_topology_change_stops_visible_output(self):
        self.fake_active()
        self.live.output_window = Mock()
        self.live.output_window.isVisible.return_value = True
        self.live.screensChanged()
        self.live.output_window.hide.assert_called_once()
        self.assertTrue(self.live.stopping)
        self.assertTrue(self.live.provider.image.isNull())

    def test_hidden_output_cannot_count_presentations(self):
        self.fake_active()
        self.live.output_window = Mock()
        self.live.output_window.isVisible.return_value = False
        self.live.output_pending = time.perf_counter_ns()
        self.live.outputFrameSwapped()
        self.assertEqual(self.live.output_presented, 0)

    def test_output_metrics_bounded_and_cleared_on_stop(self):
        self.fake_active()
        self.live.output_window = Mock()
        self.live.output_window.isVisible.return_value = True
        for _ in range(1000):
            self.live.output_pending = time.perf_counter_ns()
            self.live.outputFrameSwapped()
        self.assertEqual(len(self.live.output_latencies), 512)
        self.live.stop()
        self.assertIsNone(self.live.output_pending)


if __name__ == "__main__":
    unittest.main()
