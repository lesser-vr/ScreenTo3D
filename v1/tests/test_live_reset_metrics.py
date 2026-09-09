import unittest

from depthsbs_app.live_sbs import (
    RESETS, RESET_START, RESET_RESIZE, RESET_GAP, RESET_CUT, STAT_COUNT,
    record_reset, reset_reason,
)


class ResetMetricsTests(unittest.TestCase):
    def test_completed_resets_count_exactly_once(self):
        stats = [0] * STAT_COUNT
        for reason in ("start", "gap", "gap", "resize", "cut"):
            record_reset(stats, reason)
        self.assertEqual(stats[RESETS], 5)
        self.assertEqual([stats[i] for i in
                          (RESET_START, RESET_RESIZE, RESET_GAP, RESET_CUT)],
                         [1, 1, 2, 1])
        self.assertEqual(sum(stats[30:34]), stats[RESETS])
        self.assertEqual(stats[3:30], [0] * 27)

    def test_unknown_reason_does_not_modify_metrics(self):
        stats = [0] * STAT_COUNT
        with self.assertRaises(KeyError):
            record_reset(stats, "unknown")
        self.assertEqual(stats, [0] * STAT_COUNT)

    def test_gap_precedes_cut_and_resize_precedes_gap(self):
        shape = (3840, 2160)
        self.assertEqual(reset_reason(1, 4, shape, shape, True), "gap")
        self.assertEqual(reset_reason(1, 4, shape, (1920, 1080), True), "resize")
        self.assertEqual(reset_reason(None, 4, None, shape, True), "start")
        self.assertIsNone(reset_reason(4, 5, shape, shape, False))


if __name__ == "__main__":
    unittest.main()
