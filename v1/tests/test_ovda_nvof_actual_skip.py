import unittest

from evaluate_ovda_nvof_actual_skip import (
    reset_before_fresh,
    should_infer,
    verify_attribution_video,
)


class OvdaNvofActualSkipTests(unittest.TestCase):
    def test_only_fresh_and_cut_fresh_infer(self):
        self.assertTrue(should_infer("fresh"))
        self.assertTrue(should_infer("cut-fresh"))
        self.assertFalse(should_infer("warped"))
        with self.assertRaises(ValueError):
            should_infer("held")

    def test_reset_before_fresh_isolates_previous_warp(self):
        self.assertTrue(reset_before_fresh(True, "fresh", None))
        self.assertTrue(reset_before_fresh(False, "fresh", "warped"))
        self.assertTrue(reset_before_fresh(False, "cut-fresh", "warped"))
        self.assertFalse(reset_before_fresh(False, "warped", "fresh"))
        self.assertFalse(reset_before_fresh(False, "fresh", "fresh"))

    def test_video_verifier_rejects_missing_media(self):
        with self.assertRaises(FileNotFoundError):
            verify_attribution_video("missing-attribution-video.mp4")


if __name__ == "__main__":
    unittest.main()
