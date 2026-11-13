import gc
import multiprocessing as mp
import unittest
import weakref
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from screento3d_app.capture_worker import publish_pixels
from screento3d_app.live_retained_capture import RetainedCaptureMailbox


class RetainedCaptureTests(unittest.TestCase):
    def test_default_publish_still_copies_into_fixed_storage(self):
        mailbox = RetainedCaptureMailbox.create(mp.get_context("spawn"))
        mailbox.pixels = bytearray(4 * 3 * 4)
        source = np.arange(4 * 3 * 4, dtype=np.uint8).reshape(3, 4, 4)
        publish_pixels(mailbox, source, 4, 3)
        target = np.frombuffer(mailbox.pixels, np.uint8).reshape(3, 4, 4)
        self.assertTrue(np.array_equal(target, source))
        self.assertIsNot(target, source)

    def test_candidate_retains_exact_view_and_releases_replaced_frame(self):
        mailbox = RetainedCaptureMailbox.create(mp.get_context("spawn"))
        first = np.zeros((3, 4, 4), np.uint8)
        first_ref = weakref.ref(first)
        publish_pixels(mailbox, first, 4, 3, retain_frame=True)
        self.assertIs(mailbox.pixels, first)
        del first
        gc.collect()
        self.assertIsNotNone(first_ref())

        second = np.ones((3, 4, 4), np.uint8)
        publish_pixels(mailbox, second, 4, 3, retain_frame=True)
        gc.collect()
        self.assertIsNone(first_ref())
        self.assertIs(mailbox.pixels, second)

    def test_candidate_factory_rejects_output_use(self):
        context = mp.get_context("spawn")
        with self.assertRaises(ValueError):
            RetainedCaptureMailbox.create(context, sbs=True)
        with self.assertRaises(ValueError):
            RetainedCaptureMailbox.create(context, metadata_only=True)

    def test_product_input_mailbox_has_no_unused_pixel_allocation(self):
        from screento3d_app.capture_mailbox import Mailbox

        mailbox = Mailbox.create(mp.get_context("spawn"), metadata_only=True)
        self.assertIsNone(mailbox.pixels)

    def test_capture_releases_retained_frame_before_native_stop(self):
        from screento3d_app.capture_worker import capture_worker

        mailbox = RetainedCaptureMailbox.create(mp.get_context("spawn"))
        frame = SimpleNamespace(
            width=16,
            height=16,
            frame_buffer=np.zeros((16, 16, 4), np.uint8),
            timespan=123,
        )

        class Capture:
            def __init__(self, **kwargs):
                pass

            def event(self, handler):
                setattr(self, handler.__name__, handler)
                return handler

            def start_free_threaded(self):
                self.on_frame_arrived(frame, self)
                return self

            def is_finished(self):
                return True

            def stop(self):
                self.assert_released()

            def assert_released(self):
                if mailbox.pixels is not None:
                    raise AssertionError("Mapped frame retained during native stop")

        with (
            patch.dict(
                "sys.modules",
                {"windows_capture": SimpleNamespace(WindowsCapture=Capture)},
            ),
            patch("screento3d_app.capture_sources.enable_capture_dpi"),
            patch("screento3d_app.capture_sources.validate_source"),
        ):
            capture_worker(
                {"kind": "window", "id": 1},
                False,
                mailbox,
                retain_frame=True,
            )
        self.assertIsNone(mailbox.pixels)


if __name__ == "__main__":
    unittest.main()
