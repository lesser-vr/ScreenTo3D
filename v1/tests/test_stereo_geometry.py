"""Physical left/right geometry, independent of implementation-to-implementation parity."""
import unittest
from dataclasses import replace

import numpy as np

from depthsbs_app.config import MODES
from depthsbs_app.pipeline import StereoSynthesizer
from depthsbs_app.stereo import project_eye


def geometry_fixture(width=256, height=72):
    """Three textured planes: far, screen, near, with one identifiable vertical bar."""
    frame = np.zeros((height, width, 3), np.uint8)
    frame[:, width // 2 - 2:width // 2 + 2] = (255, 80, 40)
    depth = np.zeros((1, height, width), np.float32)
    depth[:, height // 3:2 * height // 3] = .5
    depth[:, 2 * height // 3:] = 1
    return frame, depth


def measure_planes(sbs):
    height, packed_width = sbs.shape[:2]
    width = packed_width // 2
    rows = (height // 6, height // 2, 5 * height // 6)
    result = {}
    for name, row in zip(("far", "screen", "near"), rows):
        left = np.flatnonzero(sbs[row, :width, 0] == 255)
        right = np.flatnonzero(sbs[row, width:, 0] == 255)
        if not len(left) or not len(right):
            raise AssertionError(f"Missing {name} marker")
        result[name] = float(left.mean() - right.mean())
    return result


class StereoGeometryTests(unittest.TestCase):
    def test_near_is_crossed_far_is_uncrossed_in_lr_sbs(self):
        frame, depth = geometry_fixture()
        policy = replace(MODES["balanced"], divergence=.125, convergence=.5,
                         depth_guide_radius=1, flat_background_refinement=False)

        def pair(rgb, aligned, left_shift, **kwargs):
            return (project_eye(rgb, aligned, left_shift, **kwargs),
                    project_eye(rgb, aligned, -left_shift, **kwargs))

        for paired in (None, pair):
            with self.subTest(paired=paired is not None):
                output = StereoSynthesizer(256, 72, policy, paired_projection=paired).render(frame, depth)
                # Rays from left/right eyes intersect in front of the display only
                # when the left-eye marker is RIGHT of the right-eye marker.
                actual = measure_planes(output)
                self.assertEqual(actual, {"far": -16., "screen": 0., "near": 16.})


if __name__ == "__main__":
    unittest.main()
