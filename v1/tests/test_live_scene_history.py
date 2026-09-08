import unittest
from unittest.mock import patch

import cv2
import numpy as np

from depthsbs_app.live_scene_history import LiveSceneHistory


class LiveSceneHistoryTests(unittest.TestCase):
    def test_exact_old_predicate_across_shapes_and_thresholds(self):
        rng = np.random.default_rng(731)
        cases = 0
        for height, width in ((16, 17), (180, 320), (1080, 1920)):
            for threshold in (0.0, 0.1, 0.18, 0.5, 1.0):
                history = LiveSceneHistory(threshold)
                previous = None
                for index in range(12):
                    frame = rng.integers(0, 256, (height, width, 3), dtype=np.uint8)
                    if index % 3 == 0:
                        frame.fill(index * 20)
                    if index == 7:
                        history.reset()
                        previous = None
                    expected = previous is not None and (
                        float(
                            np.mean(
                                np.abs(
                                    cv2.resize(frame, (32, 32)).astype(np.float32)
                                    - cv2.resize(previous, (32, 32)).astype(np.float32)
                                )
                            )
                        )
                        / 255
                        > threshold
                    )
                    sample = history.inspect(frame)
                    self.assertEqual(sample.cut, expected)
                    history.commit(sample)
                    previous = frame.copy()
                    cases += 1
        self.assertEqual(cases, 180)

    def test_one_resize_and_compact_owned_history(self):
        frame = np.full((1080, 1920, 3), 123, np.uint8)
        history = LiveSceneHistory(0.18)
        with patch(
            "depthsbs_app.live_scene_history.cv2.resize", wraps=cv2.resize
        ) as resize:
            sample = history.inspect(frame)
            history.validate(sample, frame)
            history.commit(sample)
            self.assertEqual(resize.call_count, 1)
        self.assertEqual(history.previous.nbytes, 32 * 32 * 3 * 4)
        frame.fill(0)
        self.assertTrue(np.all(history.previous == 123))
        self.assertFalse(history.previous.flags.writeable)
        history.reset()
        self.assertIsNone(history.previous)

    def test_observation_cannot_cross_frame_reset_or_commit(self):
        frame = np.zeros((16, 16, 3), np.uint8)
        history = LiveSceneHistory(0.18)
        sample = history.inspect(frame)
        with self.assertRaises(ValueError):
            history.validate(sample, frame.copy())
        with self.assertRaises(ValueError):
            LiveSceneHistory(0.18).validate(sample, frame)
        history.commit(sample)
        with self.assertRaises(ValueError):
            history.commit(sample)
        sample = history.inspect(frame)
        history.reset()
        with self.assertRaises(ValueError):
            history.validate(sample, frame)



if __name__ == "__main__":
    unittest.main()
