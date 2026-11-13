import unittest

from screento3d_app.live_sbs import (
    RESETS, RESET_START, RESET_RESIZE, RESET_GAP, RESET_CUT, STAT_COUNT,
    record_reset, reset_reason,
    record_ovda_inference, OVDA_CACHE_USED, OVDA_CACHE_SUM, OVDA_FULL_CONTEXT,
    OVDA_STREAK, OVDA_STREAK_MAX,
)


class ResetMetricsTests(unittest.TestCase):
    def test_ovda_occupancy_counts_pre_inference_context(self):
        stats=[0]*STAT_COUNT
        for used in range(16):record_ovda_inference(stats,used)
        record_ovda_inference(stats,15)
        self.assertEqual(stats[OVDA_CACHE_USED],15)
        self.assertEqual(stats[OVDA_FULL_CONTEXT],2)
        self.assertEqual(stats[OVDA_CACHE_SUM],sum(range(16))+15)
        self.assertEqual(stats[OVDA_STREAK_MAX],17)
        record_reset(stats,'cut')
        self.assertEqual(stats[OVDA_STREAK],0)
        record_ovda_inference(stats,0)
        self.assertEqual(stats[OVDA_STREAK],1)
        self.assertEqual(stats[OVDA_STREAK_MAX],17)
        for invalid in (-1,16,True,None):
            snapshot=stats.copy()
            with self.assertRaises(ValueError):record_ovda_inference(stats,invalid)
            self.assertEqual(stats,snapshot)

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
