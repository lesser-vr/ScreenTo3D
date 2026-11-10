import unittest
from unittest.mock import Mock, patch

from depthsbs_app.live_gpu_candidate import DEFAULT_RESOLVE, LiveGpuCandidate
from depthsbs_app.live_policy import resolve_live
from depthsbs_app.live_sbs import STAT_COUNT


class LiveResolveTests(unittest.TestCase):
    def test_invalid_diagnostic_choice_fails_before_gpu_allocation(self):
        engine = Mock()
        for value in ("", "auto", "PARALLEL", "1"):
            with (
                self.subTest(value=value),
                patch.dict("os.environ", {"DEPTHSBS_LIVE_RESOLVE": value}),
            ):
                with self.assertRaisesRegex(ValueError, "serial or parallel"):
                    LiveGpuCandidate(320, 180, resolve_live("balanced"), engine)
        engine._device_check.assert_not_called()

    def test_metrics_remain_fixed_capacity(self):
        self.assertEqual(STAT_COUNT, 43)

    def test_exact_parallel_is_the_promoted_default(self):
        self.assertEqual(DEFAULT_RESOLVE, "parallel")


if __name__ == "__main__":
    unittest.main()
