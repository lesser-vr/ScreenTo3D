import multiprocessing as mp
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from screento3d_app.capture_telemetry import (
    CAPACITY,
    FIELDS,
    CaptureTelemetry,
    CaptureRecorder,
    observation_rates,
)


def record_child(shared):
    recorder = CaptureRecorder(shared)
    recorder.observe(100, 120, 10, 0)
    recorder.finish()


class CaptureTelemetryTests(unittest.TestCase):
    def setUp(self):
        self.shared = CaptureTelemetry.create(mp.get_context("spawn"))
        self.recorder = CaptureRecorder(self.shared)

    def test_ring_is_bounded_and_ordered(self):
        for i in range(CAPACITY * 3):
            self.recorder.observe(i * 10, i * 10 + 3, i, i % 3)
        snapshot = self.shared.snapshot(history=True)
        self.assertEqual(len(self.shared.events), CAPACITY * FIELDS)
        self.assertEqual(len(snapshot["events"]), CAPACITY)
        self.assertEqual(snapshot["events"][0][0], CAPACITY * 2 + 1)
        self.assertEqual(snapshot["events"][-1][0], CAPACITY * 3)
        self.assertEqual(snapshot["callbacks"], CAPACITY * 3)
        self.assertEqual(snapshot["published"], CAPACITY)
        self.assertEqual(snapshot["contention"], CAPACITY)
        self.assertEqual(snapshot["failed"], CAPACITY)

    def test_nonblocking_diagnostics_do_not_lose_cumulative_outcomes(self):
        with self.shared.lock:
            self.recorder.observe(10, 20, 0, 1)
            self.assertIsNone(self.shared.snapshot())
            self.recorder.finish()
        self.recorder.observe(30, 40, 1, 0)
        snapshot = self.shared.snapshot(history=True)
        self.assertEqual(snapshot["callbacks"], 2)
        self.assertEqual(snapshot["contention"], 1)
        self.assertEqual(snapshot["missing_events"], 1)
        self.assertEqual([r[0] for r in snapshot["events"]], [2])
        self.assertFalse(snapshot["complete"])
        self.recorder.finish()
        self.assertTrue(self.shared.snapshot()["complete"])

    def test_missing_or_restarted_samples_are_not_zero_rates(self):
        self.assertIsNone(observation_rates(None, self.shared.snapshot()))
        before = self.shared.snapshot()
        after = dict(
            before,
            snapshot_ns=before["snapshot_ns"] + 1_000_000_000,
            callbacks=2,
            published=1,
            contention=1,
        )
        result = observation_rates(before, after)
        self.assertEqual(result["callbacks_fps"], 2)
        self.assertEqual(result["published_fps"], 1)
        with self.assertRaises(ValueError):
            observation_rates(before, dict(after, session_id=before["session_id"] + 1))
        with self.assertRaises(ValueError):
            observation_rates(after, before)

    def test_spawn_transports_independent_counters(self):
        child = mp.get_context("spawn").Process(
            target=record_child, args=(self.shared,)
        )
        child.start()
        child.join(10)
        try:
            self.assertEqual(child.exitcode, 0)
            snapshot = self.shared.snapshot(history=True)
            self.assertEqual(snapshot["events"], [[1, 100, 120, 10, 0]])
            self.assertTrue(snapshot["complete"])
        finally:
            if child.is_alive():
                child.terminate()
                child.join(5)

    def test_callback_counts_publication_and_lock_drop_independently(self):
        from screento3d_app.capture_mailbox import Mailbox, RECEIVED
        from screento3d_app.capture_worker import capture_worker

        mailbox = Mailbox.create(mp.get_context("spawn"))
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
                with mailbox.lock:
                    self.on_frame_arrived(frame, self)
                self.on_frame_arrived(frame, self)
                return self

            def is_finished(self):
                return True

            def stop(self):
                pass

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
                capture_telemetry=self.shared,
            )
        snapshot = self.shared.snapshot(history=True)
        self.assertEqual(snapshot["callbacks"], 3)
        self.assertEqual(snapshot["published"], 2)
        self.assertEqual(snapshot["contention"], 1)
        self.assertEqual(snapshot["failed"], 0)
        self.assertTrue(snapshot["complete"])
        self.assertEqual(mailbox.meta[RECEIVED], 3)
        self.assertEqual([r[4] for r in snapshot["events"]], [0, 1, 0])


if __name__ == "__main__":
    unittest.main()
