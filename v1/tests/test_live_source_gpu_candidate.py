import unittest
from unittest.mock import Mock

import numpy as np

from depthsbs_app.live_source_gpu_candidate import LiveSourceGpuCandidate


class LiveSourceGpuCandidateTests(unittest.TestCase):
    def candidate(self):
        value = LiveSourceGpuCandidate.__new__(LiveSourceGpuCandidate)
        value.width, value.height = 320, 180
        value.engine = Mock()
        value.engine.profile = (518, 924)
        value.engine.stream.cuda_stream = 123
        value.h2d = 0
        value._owner = Mock()
        return value

    def test_infer_requires_owned_depth_on_the_engine_stream(self):
        candidate = self.candidate()
        depth = Mock(owner=candidate.engine, stream=123)
        candidate.engine.infer_device.return_value = depth
        frame = np.zeros((180, 320, 3), np.uint8)
        self.assertIs(candidate.infer(frame), depth)
        depth.validate.assert_called_once_with()
        self.assertEqual(candidate.h2d, 3 * 518 * 924 * 4)

        depth.stream = 456
        with self.assertRaisesRegex(ValueError, "CUDA stream"):
            candidate.infer(frame)

    def test_invalid_profile_fails_before_device_submission(self):
        candidate = self.candidate()
        candidate.engine.profile = None
        with self.assertRaisesRegex(ValueError, "profile"):
            candidate.infer(np.zeros((180, 320, 3), np.uint8))
        candidate.engine.infer_device.assert_not_called()

    def test_vda_input_shape_is_counted(self):
        candidate = self.candidate()
        candidate.engine.profile = None
        candidate.engine.input_shape = (1, 1, 3, 518, 924)
        self.assertEqual(candidate._input_bytes(), 3 * 518 * 924 * 4)


if __name__ == "__main__":
    unittest.main()
