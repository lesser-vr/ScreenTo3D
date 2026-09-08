"""Small guards for live benchmark CPU and summary measurements."""

import os
import unittest

from benchmark_live_modes import process_cpu_seconds
from summarize_native_1080p import distribution


class LiveBenchmarkMetricsTests(unittest.TestCase):
    def test_owned_process_cpu_is_monotonic(self):
        before = process_cpu_seconds(os.getpid())
        sum(i * i for i in range(100_000))
        after = process_cpu_seconds(os.getpid())
        self.assertGreaterEqual(before, 0)
        self.assertGreaterEqual(after, before)

    def test_invalid_process_is_not_zero_usage(self):
        with self.assertRaises(OSError):
            process_cpu_seconds(0)

    def test_missing_samples_are_not_zero(self):
        self.assertIsNone(distribution([]))
        result = distribution([1, 2, 3, 4, 5])
        self.assertEqual(result["count"], 5)
        self.assertEqual(result["p50"], 3)
        self.assertEqual(result["minimum"], 1)
        self.assertEqual(result["maximum"], 5)


if __name__ == "__main__":
    unittest.main()
