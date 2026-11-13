import ctypes as ct
import threading
import unittest
from unittest.mock import Mock, patch

from screento3d_app.motion_history import MotionHistory, LAYOUTS
from screento3d_app.stereo_stability import DepthRangeClock
from screento3d_app.live_gpu_candidate import LiveGpuCandidate


class MotionHistoryTests(unittest.TestCase):
    def session(self):
        session = MotionHistory.__new__(MotionHistory)
        session.thread = threading.get_ident()
        session.failed = False
        session.handle = ct.c_void_p(1)
        session.clock = DepthRangeClock()
        session.reset_pending = True
        session.dll = Mock()
        session.dll.motion_apply.return_value = 1
        session.dll.motion_destroy.return_value = 1
        session.dll.motion_last_error.return_value = b"Injected failure"
        return session

    def test_untrusted_layout_or_dll_never_loads_native_code(self):
        with patch("screento3d_app.motion_history.ct.CDLL") as load:
            with self.assertRaises(ValueError):
                MotionHistory(32, 32, 1, "unknown")
            with patch("pathlib.Path.read_bytes", return_value=b"changed"):
                with self.assertRaises(ValueError):
                    MotionHistory(32, 32, 1, next(iter(LAYOUTS)))
            load.assert_not_called()

    def test_failure_is_terminal_but_owned_resources_can_close(self):
        session = self.session()
        session.dll.motion_apply.return_value = 0
        with self.assertRaisesRegex(RuntimeError, "Injected"):
            session.apply(2, 1_000_000_000)
        with self.assertRaisesRegex(RuntimeError, "failed/closed"):
            session.apply(2, 1_030_000_000)
        self.assertEqual(session.dll.motion_apply.call_count, 1)
        session.close()
        session.close()
        session.dll.motion_destroy.assert_called_once()

    def test_foreign_owner_cannot_release_or_submit(self):
        session = self.session()
        session.thread = -1
        with self.assertRaises(RuntimeError):
            session.apply(2, 1_000_000_000)
        with self.assertRaises(RuntimeError):
            session.close()
        session.dll.motion_apply.assert_not_called()
        session.dll.motion_destroy.assert_not_called()
        self.assertEqual(session.handle.value, 1)

    def test_cleanup_error_does_not_replace_primary_failure(self):
        session = self.session()
        session.dll.motion_destroy.return_value = 0
        primary = ValueError("primary")
        session.__exit__(ValueError, primary, None)
        self.assertIn("Injected", primary.__notes__[0])
        self.assertIsNone(session.handle.value)

    def test_renderer_releases_borrowed_layout_after_motion_close_failure(self):
        renderer = LiveGpuCandidate.__new__(LiveGpuCandidate)
        renderer.thread = threading.get_ident()
        renderer.handle = ct.c_void_p(2)
        renderer.motion_history = Mock()
        renderer.motion_history.close.side_effect = RuntimeError("motion close failure")
        renderer.dll = Mock()
        renderer.dll.live_destroy.return_value = 0
        renderer.scene_history = Mock()
        with self.assertRaisesRegex(RuntimeError, "motion close failure"):
            renderer.close()
        renderer.dll.live_destroy.assert_called_once()
        renderer.scene_history.reset.assert_called_once()
        self.assertIsNone(renderer.handle.value)
        self.assertIsNone(renderer.motion_history)


if __name__ == "__main__":
    unittest.main()
