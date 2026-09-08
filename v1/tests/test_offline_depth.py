import unittest

import numpy as np
from depthsbs_app.offline_depth import CenteredDepthWindow, is_scene_cut


def frame(value, shape=(8, 12, 3)):
    return np.full(shape, value, np.uint8)


def depth(offset=0.0, shape=(8, 12)):
    values = np.linspace(0.1, 0.9, shape[0] * shape[1], dtype=np.float32)
    return (values.reshape(shape) + offset)[None]


class OfflineDepthWindowTests(unittest.TestCase):
    def test_scene_cut_predicate_is_fixed_size_and_strict(self):
        old = frame(0, (32, 48, 3))
        self.assertFalse(is_scene_cut(old, frame(25, (64, 96, 3)), 0.10))
        self.assertTrue(is_scene_cut(old, frame(255, (64, 96, 3)), 0.10))
        with self.assertRaises(ValueError):
            is_scene_cut(old.astype(np.float32), old, 0.10)

    def test_order_ownership_future_context_and_bounds(self):
        window = CenteredDepthWindow(radius=1)
        inputs = [frame(value) for value in (10, 10, 10)]
        output = []
        self.assertEqual(window.submit(inputs[0], depth(0.00)), [])
        output.extend(window.submit(inputs[1], depth(0.01)))
        inputs[0][:] = 255
        output.extend(window.submit(inputs[2], depth(0.02)))
        output.extend(window.finish())
        self.assertEqual(len(output), 3)
        self.assertTrue(np.all(output[0][0] == 10))
        self.assertTrue(all(item[1].dtype == np.float32 for item in output))
        report = window.telemetry()
        self.assertEqual(report["submitted_frames"], 3)
        self.assertEqual(report["emitted_frames"], 3)
        self.assertGreaterEqual(report["future_context_frames"], 2)
        self.assertLessEqual(report["max_resident_samples"], 3)
        self.assertTrue(report["bounded"])

    def test_motion_gate_preserves_target_depth(self):
        reference = CenteredDepthWindow(radius=1)
        reference.submit(frame(0), depth())
        expected = reference.finish()[0][1]

        window = CenteredDepthWindow(radius=1)
        window.submit(frame(0), depth())
        actual = window.submit(frame(255), depth(0.4))[0][1]
        np.testing.assert_array_equal(actual, expected)

    def test_cut_flush_does_not_cross_scene_boundary(self):
        reference = CenteredDepthWindow(radius=1)
        reference.submit(frame(10), depth())
        expected = reference.finish()[0][1]

        window = CenteredDepthWindow(radius=1)
        window.submit(frame(10), depth())
        flushed = window.submit(frame(10), depth(0.4), cut_before=True)
        np.testing.assert_array_equal(flushed[0][1], expected)
        window.finish()
        report = window.telemetry()
        self.assertEqual(report["scenes"], 2)
        self.assertEqual(report["cut_flushes"], 1)

    def test_invalid_input_and_lifecycle_are_rejected(self):
        with self.assertRaises(ValueError):
            CenteredDepthWindow(radius=0)
        window = CenteredDepthWindow(radius=1)
        with self.assertRaises(ValueError):
            window.submit(frame(0).astype(np.float32), depth())
        with self.assertRaises(ValueError):
            window.submit(frame(0), depth().astype(np.float64))
        window.submit(frame(0), depth())
        window.finish()
        with self.assertRaises(RuntimeError):
            window.submit(frame(0), depth())


if __name__ == "__main__":
    unittest.main()
