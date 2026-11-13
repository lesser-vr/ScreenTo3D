import unittest
from screento3d_app.presentation_policy import PresentationCadence, WorkCadence, NativeDeliveryCadence, delivery_cadence


class CadenceTests(unittest.TestCase):
    def test_work_recovers_jitter_without_accumulating_delay(self):
        for hz in (30, 60):
            c = WorkCadence(hz)
            c.emitted(1_000_000_000)
            stamps = []
            for _ in range(1000):
                now = c.next_ns + 1_400_000
                stamps.append(now)
                c.emitted(now)
                self.assertFalse(c.ready(now))
            self.assertEqual(stamps[-1] - stamps[0], 999 * c.period_ns)

    def test_work_stall_resets_and_waits_are_bounded(self):
        c = WorkCadence(60)
        c.emitted(1_000_000_000)
        c.emitted(5_000_000_000)
        self.assertEqual(c.next_ns, 5_000_000_000 + c.period_ns)
        self.assertAlmostEqual(c.wait_seconds(5_000_000_000), c.period_ns / 1e9)
        self.assertEqual(c.wait_seconds(1), .05)
        self.assertEqual(c.wait_seconds(c.next_ns), .001)

    def test_only_non_vfg_native_uses_short_guard(self):
        for native, vfg in ((False, False), (False, True), (True, True)):
            self.assertIs(type(delivery_cadence(60, native=native, vfg=vfg)), PresentationCadence)
        c = delivery_cadence(60, native=True, vfg=False)
        self.assertIs(type(c), NativeDeliveryCadence)
        c.emitted(100)
        self.assertFalse(c.ready(100 + c.period_ns - 3_000_000 - 1))
        self.assertTrue(c.ready(100 + c.period_ns - 3_000_000))
        for cls in (WorkCadence, NativeDeliveryCadence):
            c = cls(0)
            c.emitted(100)
            self.assertTrue(c.ready(100))

    def test_targets(self):
        for hz in (30, 60):
            cadence = PresentationCadence(hz)
            self.assertEqual(cadence.period_ns, round(1e9 / hz))
        for invalid in (120, -1, True, 30.0, '60', None):
            with self.assertRaises(ValueError):
                PresentationCadence(invalid)

    def test_default_is_unlimited(self):
        c = PresentationCadence()
        self.assertEqual(c.hz, 0)
        self.assertEqual(c.period_ns, 0)
        self.assertEqual(c.poll_ms, 1)
        c.emitted(100)
        self.assertTrue(c.ready(100))
        self.assertTrue(c.ready(101))

    def test_no_burst_after_delay(self):
        c = PresentationCadence(60)
        c.emitted(1_000_000_000)
        self.assertFalse(c.ready(1_000_000_001))
        c.emitted(5_000_000_000)
        self.assertEqual(c.next_ns, 5_000_000_000 + c.period_ns)

    def test_late_poll_never_shortens_next_interval(self):
        c = PresentationCadence(30)
        c.emitted(1_000_000_000)
        target = c.next_ns
        c.emitted(target + 2_000_000)
        self.assertEqual(c.next_ns, target + 2_000_000 + c.period_ns)
        self.assertFalse(c.ready(c.next_ns - 1))
        self.assertTrue(c.ready(c.next_ns))
