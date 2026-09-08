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
        self.desktop.live = self.live

    def test_file_work_prevents_capture(self):
        self.desktop.lease.acquire("file")
        self.live.start()
        self.assertFalse(self.live.active)
        self.assertEqual(self.desktop.lease.owner, "file")

    def test_local_gui_defaults_to_gpu(self):
        with patch("depthsbs_app.live_preview.os.environ", {}):
            live = LivePreview(self.desktop)
        self.assertEqual(live.processingPath, "gpu")
        self.assertEqual(live.presentationHz, 30)

    def test_explicit_reference_environment_remains_available(self):
        with patch(
            "depthsbs_app.live_preview.os.environ", {"DEPTHSBS_LIVE_GPU_CANDIDATE": "0"}
        ):
            live = LivePreview(self.desktop)
        self.assertEqual(live.processingPath, "reference")

    def test_native_is_explicit_and_locked_while_active(self):
        self.live.setSbs(True)
        with patch("depthsbs_app.native_delivery.NativeDelivery"):
            self.live.setProcessingPath("gpu-texture")
        self.assertTrue(self.live.nativeEnabled)
        self.assertTrue(self.live.gpu_candidate)
        self.fake_active()
        self.live.setProcessingPath("gpu")
        self.assertEqual(self.live.processingPath, "gpu-texture")
        self.live.stop()
        self.live.native.end.assert_called_once()

    def test_native_load_failure_does_not_select_or_start_it(self):
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
        self.live.setPresentationHz(60)
        self.assertEqual(self.live.processingPath, "gpu")
        self.assertEqual(self.live.presentationHz, 60)
        self.fake_active()
        self.live.setProcessingPath("reference")
        self.live.setPresentationHz(30)
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
