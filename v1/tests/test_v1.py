import unittest

import numpy as np

from screento3d_app.config import MODES
from screento3d_app.pipeline import StereoSynthesizer, preprocess


class ModePolicyTests(unittest.TestCase):
    def test_all_user_modes_are_resolved(self):
        self.assertEqual(
            set(MODES),
            {"performance", "balanced", "video-quality", "offline-quality"},
        )
        for name, policy in MODES.items():
            self.assertEqual(policy.name, name)
            self.assertGreaterEqual(policy.inference_cadence, 1)
            self.assertGreater(policy.divergence, 0.0)
            self.assertGreater(policy.temporal_alpha, 0.0)
            self.assertLessEqual(policy.temporal_alpha, 1.0)


class PixelContractTests(unittest.TestCase):
    def test_preprocess_is_nchw_fp32_and_finite(self):
        frame = np.zeros((90, 160, 3), dtype=np.uint8)
        frame[:, :, 0] = np.arange(160, dtype=np.uint8)[None, :]
        tensor = preprocess(frame)
        self.assertEqual(tensor.shape, (1, 3, 518, 518))
        self.assertEqual(tensor.dtype, np.float32)
        self.assertTrue(np.isfinite(tensor).all())

    def test_stereo_output_is_double_width(self):
        height, width = 48, 64
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :, 0] = np.arange(width, dtype=np.uint8)[None, :]
        depth = np.linspace(0.0, 1.0, 518 * 518, dtype=np.float32).reshape(1, 518, 518)
        output = StereoSynthesizer(width, height, MODES["balanced"]).render(frame, depth)
        self.assertEqual(output.shape, (height, width * 2, 3))
        self.assertEqual(output.dtype, np.uint8)


if __name__ == "__main__":
    unittest.main()
