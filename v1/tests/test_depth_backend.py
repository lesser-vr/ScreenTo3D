import unittest
from unittest.mock import Mock
import numpy as np

from screento3d_app.config import MODES
from screento3d_app.depth_backend import BackendBinding, BackendSpec, resolve_backend


class DepthBindingTests(unittest.TestCase):
    def binding(self, **values):
        return BackendBinding(BackendSpec('test', 'fake', **values), Mock(), lambda x: x)

    def test_unavailable_model_does_not_fallback(self):
        factory = Mock()
        with self.assertRaisesRegex(ValueError, 'not installed/validated'):
            resolve_backend('unavailable', factory, lambda x: x)
        factory.assert_not_called()

    def test_legacy_policy_backend_remains_available_for_low_level_oracles(self):
        for policy in MODES.values():
            binding = resolve_backend(policy.depth_backend, Mock(), lambda x: x)
            binding.validate_policy(policy)
            self.assertEqual(binding.describe()['model_id'], 'da2-small')

    def test_stateful_requires_every_frame(self):
        with self.assertRaisesRegex(ValueError, 'every frame'):
            self.binding(stateful=True).validate_policy(MODES['performance'])
        self.binding(stateful=True).validate_policy(MODES['video-quality'])

    def test_reset_is_explicit_for_stateful_only(self):
        engine = Mock()
        binding = self.binding(stateful=True)
        for reason in ('start', 'scene_cut', 'source_change', 'discontinuity'):
            binding.reset(engine, reason)
        self.assertEqual(engine.reset.call_count, 4)
        self.binding().reset(engine, 'start')
        self.assertEqual(engine.reset.call_count, 4)
        with self.assertRaises(ValueError):
            binding.reset(engine, 'invalid')
        with self.assertRaises(TypeError):
            binding.reset(object(), 'start')

    def test_result_owns_buffer(self):
        shared = np.ones((1, 2, 3), np.float32)
        result = self.binding().infer(Mock(infer=Mock(return_value=shared)), None)
        shared[:] = 0
        np.testing.assert_array_equal(result, np.ones_like(result))

    def test_invalid_depth_rejected(self):
        for depth in (np.ones((1, 2, 3), np.float64), np.ones((2, 3), np.float32),
                      np.full((1, 2, 3), np.nan, np.float32), np.ones((1, 0, 3), np.float32)):
            with self.subTest(shape=depth.shape), self.assertRaises(ValueError):
                self.binding().infer(Mock(infer=Mock(return_value=depth)), None)

    def test_unknown_polarity_rejected(self):
        with self.assertRaisesRegex(ValueError, 'polarity'):
            self.binding(polarity='metric').validate_policy(MODES['balanced'])
