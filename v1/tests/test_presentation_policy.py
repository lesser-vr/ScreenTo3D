import unittest
from depthsbs_app.presentation_policy import PresentationCadence


class CadenceTests(unittest.TestCase):
    def test_targets(self):
        for hz in (30, 60):
            cadence = PresentationCadence(hz)
            self.assertEqual(cadence.period_ns, round(1e9 / hz))
        with self.assertRaises(ValueError):
            PresentationCadence(120)

    def test_no_burst_after_delay(self):
        c = PresentationCadence(60)
        c.emitted(1_000_000_000)
        self.assertFalse(c.ready(1_000_000_001))
        c.emitted(5_000_000_000)
        self.assertEqual(c.next_ns, 5_000_000_000 + c.period_ns)

    def test_preserves_deadline_instead_of_adding_poll_jitter(self):
        c = PresentationCadence(30)
        c.emitted(1_000_000_000)
        target = c.next_ns
        c.emitted(target + 2_000_000)
        self.assertEqual(c.next_ns, target + c.period_ns)
