import unittest

from benchmark_guard import OutputRateGuard


class GuardTests(unittest.TestCase):
    def test_healthy_then_collapse(self):
        guard = OutputRateGuard(20, 0, 0)
        self.assertIsNone(guard.observe(3, 180))
        self.assertEqual(guard.observe(6, 195)["output_fps"], 5)

    def test_window_required(self):
        guard = OutputRateGuard(20, 0, 0)
        self.assertIsNone(guard.observe(2, 0))
        self.assertIsNotNone(guard.observe(3, 0))

    def test_actual_elapsed_and_threshold(self):
        guard = OutputRateGuard(20, 0, 0)
        self.assertIsNone(guard.observe(4, 80))
        self.assertEqual(guard.observe(8, 100)["output_fps"], 5)


if __name__ == "__main__":
    unittest.main()
