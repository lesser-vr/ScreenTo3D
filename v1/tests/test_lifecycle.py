import unittest
from depthsbs_app.lifecycle import Lifecycle


class LifecycleTests(unittest.TestCase):
    def test_disjoint_intervals(self):
        times = iter([10, 12, 15, 19])
        lifecycle = Lifecycle(lambda: next(times))
        for name in ('startup', 'frames', 'drain'):
            lifecycle.checkpoint(name)
        self.assertEqual(lifecycle.seconds, dict(startup=2, frames=3, drain=4))
        self.assertEqual(sum(lifecycle.seconds.values()), 9)

    def test_duplicate_is_rejected(self):
        lifecycle = Lifecycle(lambda: 10)
        lifecycle.checkpoint('startup')
        with self.assertRaises(ValueError):
            lifecycle.checkpoint('startup')
