"""Injected GPU failures: no real screen capture; run in prepared GPU environment."""

import ctypes
import multiprocessing as mp
import unittest
import time
from unittest.mock import patch

import numpy as np

from screento3d_app.desktop_jobs import BUNDLE
from screento3d_app.resources import configure_resource_root
from screento3d_app.capture_mailbox import (
    Mailbox,
    SEQ,
    WIDTH,
    HEIGHT,
    STATE,
    RUNNING,
    FAILED,
)
from screento3d_app.live_sbs import sbs_worker, STAT_COUNT

configure_resource_root(BUNDLE)


class LiveWorkerFailures(unittest.TestCase):
    def test_zero_capture_interval_reuse_and_gap(self):
        with patch.dict("os.environ", {"SCREENTO3D_LIVE_CAPTURE_INTERVAL_MS": "0"}):
            self.test_performance_reuse_gap_and_single_pixel_refresh()

    def test_legacy_bridge_reuse_and_gap(self):
        with patch.dict("os.environ", {"SCREENTO3D_LIVE_HOST_BRIDGE": "legacy"}):
            self.test_performance_reuse_gap_and_single_pixel_refresh()

    def test_performance_reuse_gap_and_single_pixel_refresh(self):
        from screento3d_app.live_sbs import INFERRED, REUSED, PROCESSED

        context = mp.get_context("spawn")
        output = Mailbox.create(context, sbs=True)
        stats = context.RawArray(ctypes.c_longlong, STAT_COUNT)

        class Engine:
            input_bytes = output_bytes = 4

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def infer(self, tensor):
                return np.ones((1, 32, 32), np.float32)

        class Projection:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def project(self, *args, **kwargs):
                raise AssertionError("pair required")

            def project_pair(self, frame, *args, **kwargs):
                return frame.copy(), frame.copy()

        def capture(source, cursor, mailbox, **kwargs):
            for index, seq in enumerate((1, 2, 4, 5, 6, 7)):
                with mailbox.lock:
                    pixels = np.full((32, 32, 4), 127, np.uint8)
                    if index == 5:
                        pixels[0, 0, 0] = 128
                    mailbox.pixels = pixels
                    mailbox.meta[WIDTH] = mailbox.meta[HEIGHT] = 32
                    mailbox.meta[SEQ] = seq
                    mailbox.meta[STATE] = RUNNING
                end = time.perf_counter() + 2
                while output.meta[SEQ] < index + 1 and time.perf_counter() < end:
                    time.sleep(0.002)
            mailbox.stop.set()

        with (
            patch("screento3d_app.trt_backend.DepthEngine", return_value=Engine()),
            patch(
                "screento3d_app.live_projection.LiveProjection", return_value=Projection()
            ),
            patch("screento3d_app.capture_worker.capture_worker", side_effect=capture),
        ):
            sbs_worker({}, False, output, stats, 1.0, "performance")
        self.assertEqual(stats[PROCESSED], 6)
        self.assertEqual(stats[INFERRED], 4)
        self.assertEqual(stats[REUSED], 2)

    def test_inference_failure_closes_capture_projection_and_engine(self):
        closed = []

        class Engine:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                closed.append("engine")

            def infer(self, tensor):
                raise RuntimeError("injected GPU inference failure")

        class Projection:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                closed.append("projection")

            def project(self, *args, **kwargs):
                raise AssertionError(
                    "must not fall back to projection after inference error"
                )

            project_pair = project

        def capture(source, cursor, mailbox, **kwargs):
            with mailbox.lock:
                mailbox.pixels = np.full((32, 32, 4), 127, np.uint8)
                mailbox.meta[WIDTH] = mailbox.meta[HEIGHT] = 32
                mailbox.meta[SEQ] = 1
                mailbox.meta[STATE] = RUNNING
            mailbox.stop.wait(5)
            closed.append("capture")

        context = mp.get_context("spawn")
        output = Mailbox.create(context, sbs=True)
        stats = context.RawArray(ctypes.c_longlong, STAT_COUNT)
        with (
            patch("screento3d_app.trt_backend.DepthEngine", return_value=Engine()),
            patch(
                "screento3d_app.live_projection.LiveProjection", return_value=Projection()
            ),
            patch("screento3d_app.capture_worker.capture_worker", side_effect=capture),
        ):
            sbs_worker({}, False, output, stats, 1.0)
        self.assertEqual(output.meta[STATE], FAILED)
        self.assertEqual(output.meta[SEQ], 0)
        self.assertIn(b"injected GPU inference failure", output.error.value)
        self.assertEqual(closed, ["projection", "engine", "capture"])
        self.assertTrue(output.stop.is_set())


if __name__ == "__main__":
    unittest.main()
