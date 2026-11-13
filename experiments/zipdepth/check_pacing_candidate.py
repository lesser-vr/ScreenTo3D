"""Deterministic rate, spacing and pause checks for benchmark-only policies."""
import random
import unittest

from pacing_candidate import CANDIDATES, GuardedDelivery
from screento3d_app.presentation_policy import PresentationCadence


class CandidateContracts(unittest.TestCase):
    def test_delivery_guard_bounds_short_spacing_without_a_second_full_period(self):
        for hz in (30, 60):
            c = GuardedDelivery(hz)
            start = 1_000_000_000
            c.emitted(start)
            minimum = c.period_ns - 3_000_000
            self.assertFalse(c.ready(start + minimum - 1))
            self.assertTrue(c.ready(start + minimum))
            self.assertTrue(c.ready(start + c.period_ns))
        c = GuardedDelivery(0)
        c.emitted(100)
        self.assertTrue(c.ready(100))

    def test_small_lateness_does_not_accumulate(self):
        for candidate in CANDIDATES.values():
            for hz in (30, 60):
                c = candidate(hz)
                c.emitted(1_000_000_000)
                stamps = []
                for _ in range(1000):
                    now = c.next_ns + 1_400_000
                    self.assertTrue(c.ready(now))
                    stamps.append(now)
                    c.emitted(now)
                self.assertEqual(stamps[-1] - stamps[0], 999 * c.period_ns)

    def test_irregular_jitter_has_bounded_spacing_and_no_immediate_replay(self):
        for candidate in CANDIDATES.values():
            for hz in (30, 60):
                c = candidate(hz)
                c.emitted(1_000_000_000)
                previous = 1_000_000_000
                rng = random.Random(42)
                for _ in range(10000):
                    now = c.next_ns + rng.randrange(0, 8_000_000)
                    self.assertGreaterEqual(now - previous, c.period_ns - c.jitter_ns)
                    c.emitted(now)
                    self.assertFalse(c.ready(now))
                    previous = now

    def test_long_pause_restarts_without_catchup(self):
        for candidate in CANDIDATES.values():
            c = candidate(60)
            c.emitted(1_000_000_000)
            c.emitted(5_000_000_000)
            self.assertFalse(c.ready(5_000_000_000 + c.period_ns - 1))
            self.assertTrue(c.ready(5_000_000_000 + c.period_ns))

    def test_unlimited_matches_production(self):
        for candidate in CANDIDATES.values():
            c, reference = candidate(0), PresentationCadence(0)
            for now in (100, 101, 10_000, 10**10):
                c.emitted(now)
                reference.emitted(now)
                self.assertEqual(c.next_ns, reference.next_ns)
                self.assertTrue(c.ready(now))


if __name__ == '__main__':
    unittest.main()
