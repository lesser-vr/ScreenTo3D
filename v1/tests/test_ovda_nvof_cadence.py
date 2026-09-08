import unittest

import numpy as np

from evaluate_ovda_nvof_cadence import (
    THRESHOLDS,
    cadence_decision,
    output_metrics,
    summarize,
)


class OvdaNvofCadenceTests(unittest.TestCase):
    def test_cadence_forces_odd_cut_fresh_and_never_crosses_it(self):
        last_fresh = None
        actual = []
        for index in range(6):
            kind, source = cadence_decision(index, index in (0, 3), last_fresh)
            actual.append((kind, source))
            if kind != "warped":
                last_fresh = index
        self.assertEqual(
            actual,
            [
                ("fresh", 0),
                ("warped", 0),
                ("fresh", 2),
                ("cut-fresh", 3),
                ("fresh", 4),
                ("warped", 4),
            ],
        )

    def test_output_metrics_are_normalized_and_edge_aware(self):
        reference = np.zeros((24, 32, 3), np.uint8)
        reference[:, 16:] = 255
        candidate = reference.copy()
        candidate[:, 15:18] = 128
        result = output_metrics(reference, candidate)
        self.assertGreater(result["sbs_mae"], 0)
        self.assertLess(result["sbs_mae"], 1)
        self.assertGreater(result["edge_sbs_mae"], result["sbs_mae"])
        self.assertEqual(result["sbs_max_channel_error"], 128)
        self.assertGreater(result["channels_over_8_fraction"], 0)

    def test_summary_uses_predeclared_limits_and_identity_contract(self):
        rows = []
        last_fresh = None
        for index in range(60):
            kind, source = cadence_decision(index, index == 0, last_fresh)
            if kind != "warped":
                last_fresh = index
            rows.append(
                {
                    "frame": index,
                    "cut": index == 0,
                    "reference_depth_frame": index,
                    "candidate_kind": kind,
                    "candidate_source_depth_frame": source,
                    "fresh_depth_exact": True if kind != "warped" else None,
                    "valid_fraction": THRESHOLDS["minimum_warp_valid_fraction"],
                    "depth_mae": 0 if kind != "warped" else 0.01,
                    "fixed_prior_depth_mae": None if kind != "warped" else 0.011,
                    "sbs_mae": 0.001,
                    "edge_sbs_mae": 0.001,
                    "channels_over_8_fraction": 0,
                    "temporal_change_error": None if index == 0 else 0.001,
                }
            )
        result = summarize(rows)
        self.assertTrue(result["automated_gate_passed"])
        self.assertTrue(all(result["checks"].values()))


if __name__ == "__main__":
    unittest.main()
