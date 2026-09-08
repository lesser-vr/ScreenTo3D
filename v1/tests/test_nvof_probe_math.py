import unittest

import numpy as np

from nvof_device_warp import bilinear_depth_warp
from nvof_probe import expand_flow
from test_ovda_nvof import aligned_metrics, warp


class NvofMathTests(unittest.TestCase):
    def test_expand_matches_shader_cell_mapping(self):
        raw = np.array([[[32, 0], [64, 0]], [[96, 0], [128, 0]]], np.int16)
        actual = expand_flow(raw, 5, 3)
        expected_x = np.array(
            [[1, 1, 1, 2, 2], [1, 1, 1, 2, 2], [3, 3, 3, 4, 4]],
            np.float32,
        )
        np.testing.assert_array_equal(actual[:, :, 0], expected_x)

    def test_backward_warp_recovers_translation(self):
        height, width, shift = 32, 64, 4
        old = np.tile(np.arange(width, dtype=np.float32), (height, 1))
        current = np.zeros_like(old)
        current[:, shift:] = old[:, :-shift]
        flow = np.zeros((height, width, 2), np.float32)
        flow[:, :, 0] = -shift
        actual = warp(old, flow)
        np.testing.assert_array_equal(actual[:, shift:], current[:, shift:])

    def test_aligned_metric_improves_known_motion(self):
        height, width, shift = 40, 80, 4
        rng = np.random.default_rng(19)
        old_rgb = rng.integers(0, 256, (height, width, 3), np.uint8)
        rgb = np.zeros_like(old_rgb)
        rgb[:, shift:] = old_rgb[:, :-shift]
        old_depth = np.tile(np.linspace(0, 1, width, dtype=np.float32), (height, 1))
        depth = np.zeros_like(old_depth)
        depth[:, shift:] = old_depth[:, :-shift]
        backward = np.zeros((height, width, 2), np.float32)
        backward[:, :, 0] = -shift
        forward = np.zeros_like(backward)
        forward[:, :, 0] = shift
        result = aligned_metrics(old_rgb, rgb, old_depth, depth, backward, forward)
        self.assertGreater(result["valid_fraction"], 0.5)
        self.assertLess(result["warped_depth_mae"], result["fixed_depth_mae"])

    def test_device_warp_oracle_integer_translation_and_validity(self):
        height, width, shift = 12, 20, 3
        previous = np.ascontiguousarray(
            np.arange(height * width, dtype=np.float32).reshape(height, width)
        )
        flow = np.zeros((height, width, 2), np.float32)
        flow[:, :, 0] = -shift
        actual, valid = bilinear_depth_warp(previous, flow)
        expected_valid = np.zeros((height, width), np.uint8)
        expected_valid[1 : height - 2, shift + 1 : width] = 1
        np.testing.assert_array_equal(valid, expected_valid)
        mask = valid != 0
        y, x = np.mgrid[:height, :width]
        np.testing.assert_array_equal(actual[mask], previous[y[mask], x[mask] - shift])
        np.testing.assert_array_equal(actual[~mask], 0)

    def test_device_warp_oracle_fractional_bilinear(self):
        previous = np.ascontiguousarray(np.arange(64, dtype=np.float32).reshape(8, 8))
        flow = np.zeros((8, 8, 2), np.float32)
        flow[:, :, 0] = np.float32(0.5)
        flow[:, :, 1] = np.float32(0.25)
        actual, valid = bilinear_depth_warp(previous, flow)
        self.assertEqual(valid[3, 3], 1)
        expected = (
            previous[3, 3] * np.float32(0.375)
            + previous[3, 4] * np.float32(0.375)
            + previous[4, 3] * np.float32(0.125)
            + previous[4, 4] * np.float32(0.125)
        )
        self.assertAlmostEqual(float(actual[3, 3]), float(expected), places=6)

    def test_device_warp_oracle_rejects_nonfinite_depth(self):
        previous = np.zeros((8, 8), np.float32)
        previous[2, 2] = np.nan
        flow = np.zeros((8, 8, 2), np.float32)
        with self.assertRaisesRegex(ValueError, "Invalid depth-warp oracle input"):
            bilinear_depth_warp(previous, flow)


if __name__ == "__main__":
    unittest.main()
