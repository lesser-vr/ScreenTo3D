import unittest
from unittest.mock import Mock

from screento3d_app.live_policy import StaticSbsReuse


class StaticSbsTests(unittest.TestCase):
    def test_unsettled_probe_one_second_expiry_and_change(self):
        policy = StaticSbsReuse()
        renderer = Mock(syncs=0, d2h=0)
        renderer.motion_history.static_probe.side_effect = [20, 2, 0, 8]
        for i in range(1, 13):
            self.assertFalse(policy.hold(True, i))
            policy.after_render(renderer, i)
            self.assertEqual(policy.stationary, i >= 8)
        self.assertTrue(policy.hold(True, 1_000_000_011))
        self.assertFalse(policy.hold(True, 1_000_000_012))
        policy.after_render(renderer, 1_000_000_012)
        self.assertFalse(policy.hold(True, 1_000_000_013))
        self.assertFalse(policy.hold(False, 1_000_000_014))
        self.assertFalse(policy.stationary)
        self.assertFalse(policy.probed)
        self.assertEqual(renderer.syncs, 4)

    def test_isolated_duplicates_do_not_probe(self):
        policy = StaticSbsReuse()
        renderer = Mock()
        for n in range(20):
            self.assertFalse(policy.hold(n % 3 != 0, n+1))
            policy.after_render(renderer, n+1)
        renderer.motion_history.static_probe.assert_not_called()
