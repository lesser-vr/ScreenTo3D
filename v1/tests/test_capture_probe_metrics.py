import unittest
import multiprocessing as mp
from unittest.mock import patch

import numpy as np

from screento3d_app.capture_mailbox import Mailbox, SEQ, ACK, WIDTH, HEIGHT

from probe_capture_only import event_metrics, consume_host


class CaptureProbeMetricsTests(unittest.TestCase):
    def host_case(self):
        mailbox = Mailbox.create(mp.get_context("spawn"), sbs=True)
        mailbox.meta[WIDTH], mailbox.meta[HEIGHT] = 3840, 1080
        mailbox.meta[SEQ] = 7
        return mailbox, np.empty(3840 * 1080 * 4, np.uint8)

    def test_host_copy_before_ack(self):
        mailbox, buffer = self.host_case()
        mailbox.pixels[0] = 123
        self.assertTrue(consume_host(mailbox, buffer))
        self.assertEqual(buffer[0], 123)
        self.assertEqual(mailbox.meta[ACK], 7)
        self.assertFalse(consume_host(mailbox, buffer))

    def test_host_failed_copy_never_acknowledged(self):
        mailbox, buffer = self.host_case()
        with patch("probe_capture_only.np.copyto", side_effect=RuntimeError("copy")):
            with self.assertRaises(RuntimeError):
                consume_host(mailbox, buffer)
        self.assertEqual(mailbox.meta[ACK], 0)
        self.assertTrue(mailbox.lock.acquire(False))
        mailbox.lock.release()

    def test_host_wrong_dimensions_never_acknowledged(self):
        mailbox, buffer = self.host_case()
        mailbox.meta[WIDTH] = 1920
        with self.assertRaises(ValueError):
            consume_host(mailbox, buffer)
        self.assertEqual(mailbox.meta[ACK], 0)

    def test_empty_unavailable_not_zero(self):
        result = event_metrics([])
        self.assertIsNone(result["callback_duration_ms"])
        self.assertEqual(result["adjacent_pairs"], 0)

    def test_missing_ordinal_not_bridged(self):
        result = event_metrics(
            [[1, 0, 1000000, 0, 0], [3, 9000000, 10000000, 8000000, 0]]
        )
        self.assertIsNone(result["callback_interval_ms"])
        self.assertEqual(result["callback_duration_ms"]["p50"], 1)

    def test_source_clock_not_subtracted_from_callback(self):
        result = event_metrics(
            [[1, 100000000, 101000000, 0, 0], [2, 110000000, 111000000, 8000000, 0]]
        )
        self.assertEqual(result["callback_interval_ms"]["p50"], 10)
        self.assertEqual(result["source_interval_ms"]["p50"], 8)


if __name__ == "__main__":
    unittest.main()
