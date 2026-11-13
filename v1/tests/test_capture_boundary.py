import multiprocessing as mp
import unittest
from unittest.mock import patch

from screento3d_app.capture_mailbox import (
    Mailbox,
    MAX_BYTES,
    STATE,
    FAILED,
    validate_shape,
)
from screento3d_app.capture_color import require_sdr


class CaptureBoundaryTests(unittest.TestCase):
    def test_original_and_sbs_interval_defaults_are_explicit(self):
        import inspect
        from screento3d_app.capture_worker import capture_worker
        from screento3d_app.live_sbs import DEFAULT_CAPTURE_INTERVAL_MS

        self.assertEqual(
            inspect.signature(capture_worker)
            .parameters["minimum_update_interval"]
            .default,
            16,
        )
        self.assertEqual(DEFAULT_CAPTURE_INTERVAL_MS, 0)

    def test_invalid_capture_interval_fails_before_capture(self):
        from screento3d_app.capture_worker import capture_worker

        for value in (-1, 1, 16.0, True, "0", None):
            with self.subTest(value=value):
                box = Mailbox.create(mp.get_context("spawn"))
                capture_worker({}, False, box, minimum_update_interval=value)
                self.assertEqual(box.meta[STATE], FAILED)
                self.assertIn(b"Invalid capture update interval", box.error.value)

    def test_invalid_frame_ownership_mode_fails_before_capture(self):
        from screento3d_app.capture_worker import capture_worker

        for value in (0, 1, None, "retained"):
            with self.subTest(value=value):
                box = Mailbox.create(mp.get_context("spawn"))
                capture_worker({}, False, box, retain_frame=value)
                self.assertEqual(box.meta[STATE], FAILED)
                self.assertIn(b"Invalid capture frame ownership mode", box.error.value)

    def test_shape_bounds(self):
        for shape in ((16, 16), (3840, 2160), (4096, 2160)):
            validate_shape(*shape)
        for shape in ((0, 0), (15, 200), (4097, 2160), (1920, 2161)):
            with self.assertRaises(ValueError):
                validate_shape(*shape)

    def test_fixed_mailbox_and_bounded_error(self):
        box = Mailbox.create(mp.get_context("spawn"))
        self.assertEqual(len(box.pixels), MAX_BYTES)
        self.assertEqual(len(box.meta), 12)
        box.fail("오류" * 1000)
        self.assertEqual(box.meta[STATE], FAILED)
        self.assertLessEqual(len(box.error.value), 1000)
        box.stop.set()
        self.assertTrue(box.stop.is_set())

    def test_sdr_accepted(self):
        with patch(
            "screento3d_app.capture_color.display_colors",
            return_value={"test": {"enabled": False}},
        ):
            require_sdr(dict(kind="monitor", device="test"))

    def test_hdr_rejected(self):
        with patch(
            "screento3d_app.capture_color.display_colors",
            return_value={"test": {"enabled": True}},
        ):
            with self.assertRaisesRegex(ValueError, "SDR"):
                require_sdr(dict(kind="monitor", device="test"))

    def test_unknown_color_rejected(self):
        with patch("screento3d_app.capture_color.display_colors", return_value={}):
            with self.assertRaises(ValueError):
                require_sdr(dict(kind="monitor", device="test"))


if __name__ == "__main__":
    unittest.main()
