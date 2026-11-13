from dataclasses import replace
import unittest
import numpy as np

from screento3d_app.config import MODES
from screento3d_app.main import build_parser
from screento3d_app.padding import PaddingRefiner
from screento3d_app.pipeline import StereoSynthesizer


def fixture(bar=6, color=(0, 240, 0)):
    frame = np.full((100, 120, 3), color, np.uint8)
    frame[25:75, 40:80] = (120, 50, 30)
    if bar:
        frame[:, :bar] = frame[:, -bar:] = 0
    depth = np.linspace(0, 1, 12000, dtype=np.float32).reshape(100, 120)
    return frame, depth


class PaddingOptionTests(unittest.TestCase):
    def test_default_off_and_explicit_parser(self):
        self.assertFalse(build_parser().parse_args([]).letterbox_refinement)
        self.assertTrue(build_parser().parse_args(['--letterbox-refinement']).letterbox_refinement)
        self.assertTrue(all(not mode.letterbox_refinement for mode in MODES.values()))

    def test_confirmation_and_immediate_caption_invalidation(self):
        state = PaddingRefiner()
        frame, depth = fixture()
        for _ in range(2):
            self.assertIs(state.refine(frame, depth), depth)
            self.assertIsNone(state.active)
        self.assertIsNot(state.refine(frame, depth), depth)
        self.assertIsNotNone(state.active)
        caption = frame.copy()
        caption[50, 1] = 255
        self.assertIs(state.refine(caption, depth), depth)
        self.assertIsNone(state.active)
        fake_stereo = np.full((100, 240, 3), 99, np.uint8)
        self.assertIs(state.restore(fake_stereo, caption), fake_stereo)
        for _ in range(2):
            self.assertIs(state.refine(frame, depth), depth)
        self.assertIsNot(state.refine(frame, depth), depth)
        self.assertEqual(state.telemetry()['applied_frames'], 2)

    def test_changed_bounds_and_reset_require_new_confirmation(self):
        state = PaddingRefiner()
        frame, depth = fixture()
        for _ in range(3):
            state.refine(frame, depth)
        changed, depth = fixture(bar=8)
        self.assertIs(state.refine(changed, depth), depth)
        self.assertIsNone(state.active)
        state.refine(changed, depth)
        self.assertIsNot(state.refine(changed, depth), depth)
        state.reset()
        self.assertIs(state.refine(changed, depth), depth)
        self.assertEqual(state.telemetry()['scene_cut_resets'], 1)

    def test_render_preserves_padding_and_resets_at_cut(self):
        policy = replace(MODES['video-quality'], letterbox_refinement=True)
        renderer = StereoSynthesizer(120, 100, policy)
        frame, depth = fixture()
        for _ in range(3):
            output = renderer.render(frame, depth[None])
        for offset in (0, 120):
            np.testing.assert_array_equal(output[:, offset:offset+6], frame[:, :6])
            np.testing.assert_array_equal(output[:, offset+114:offset+120], frame[:, -6:])
        self.assertEqual(renderer.padding.telemetry()['restored_frames'], 1)
        changed, depth = fixture(color=(0, 0, 240))
        self.assertTrue(renderer.is_scene_cut(changed))
        first = renderer.render(changed, depth[None])
        fresh = StereoSynthesizer(120, 100, policy).render(changed, depth[None])
        np.testing.assert_array_equal(first, fresh)
        self.assertIsNone(renderer.padding.active)

    def test_no_bars_matches_existing_renderer_exactly(self):
        old = StereoSynthesizer(120, 100, MODES['video-quality'])
        new = StereoSynthesizer(120, 100, replace(MODES['video-quality'], letterbox_refinement=True))
        for i in range(5):
            frame, depth = fixture(bar=0)
            frame[30:50, 45+i:65+i] = (200, 20, 40)
            np.testing.assert_array_equal(old.render(frame, depth[None]), new.render(frame, depth[None]))
        self.assertEqual(new.padding.telemetry()['applied_frames'], 0)

    def test_invalid_confirmation_budget(self):
        for value in (0, 31, True, 2.5):
            with self.assertRaises(ValueError):
                PaddingRefiner(value)
