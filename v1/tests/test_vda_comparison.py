import unittest
from unittest.mock import Mock
import numpy as np

from vda_comparison import (BoundedEngine, inspection_sheet, lower_region,
                            validate_metadata, validate_runs)


class VdaComparisonTests(unittest.TestCase):
    def test_metadata_bounds_before_allocation(self):
        validate_metadata(dict(width=1920, height=1080, total_frames=124), 124)
        validate_metadata(dict(width=1056, height=608, total_frames=0), 124)
        for width, count, limit in ((3840, 12, 124), (1920, 125, 124),
                                    (1920, 1, 0), (1920, 1, 125), (1920, -1, 124)):
            with self.assertRaises(ValueError):
                validate_metadata(dict(width=width, height=1080, total_frames=count), limit)

    def test_actual_frame_limit_survives_scene_cut_and_cleans_up(self):
        inner = Mock()
        inner.telemetry.return_value = {}
        inner.__enter__ = Mock(return_value=inner)
        inner.__exit__ = Mock(return_value=False)
        bounded = BoundedEngine(inner, 2)
        with self.assertRaisesRegex(ValueError, 'Actual decoded'):
            with bounded:
                bounded.infer('frame0')
                bounded.reset('scene_cut')
                bounded.infer('frame1')
                self.assertEqual(bounded.telemetry()['comparison_actual_frames'], 2)
                bounded.infer('frame2')
        self.assertEqual(inner.infer.call_count, 2)
        inner.reset.assert_called_once_with('scene_cut')
        inner.__exit__.assert_called_once()

    def test_failed_inference_not_counted(self):
        inner = Mock()
        inner.infer.side_effect = RuntimeError('inference failed')
        bounded = BoundedEngine(inner, 1)
        with self.assertRaises(RuntimeError):
            bounded.infer(None)
        self.assertEqual(bounded.calls, 0)

    def test_run_count_and_source_hash_agreement(self):
        def run(count=3, digest='same'):
            return dict(frames=count, telemetry=dict(diagnostic_hashes=dict(decoded_rgb=digest)))
        validate_runs(dict(a=run(), b=run(), c=run()), 3, 3)
        validate_runs(dict(a=run(), b=run()), 0, 3)
        for runs, declared, compared in ((dict(a=run(), b=run(2)), 3, 3),
                (dict(a=run(), b=run(digest='changed')), 3, 3),
                (dict(a=run()), 4, 3), (dict(a=run(0)), 0, 0), ({}, 0, 0)):
            with self.assertRaises(ValueError):
                validate_runs(runs, declared, compared)

    def test_crop_scales_and_preserves_eye_order(self):
        self.assertEqual(lower_region(1056, 608), (200, 280, 850, 600))
        self.assertEqual(lower_region(2112, 1216), (400, 560, 1700, 1200))
        frame = np.zeros((608, 2112, 3), np.uint8)
        frame[:, :1056] = (20, 40, 60)
        frame[:, 1056:] = (80, 100, 120)
        result = inspection_sheet([('test', frame)], 1056, 608, lower=True)
        self.assertEqual(result.shape, (358, 1300, 3))
        np.testing.assert_array_equal(result[40, 0], (20, 40, 60))
        np.testing.assert_array_equal(result[40, -1], (80, 100, 120))
        full = inspection_sheet([('test', frame)], 1056, 608)
        self.assertEqual(full.shape[1], 1600)
        self.assertEqual(full.shape[0], round(608*1600/2112)+38)

    def test_bad_inspection_geometry_fails(self):
        with self.assertRaises(ValueError):
            inspection_sheet([], 1056, 608)
        with self.assertRaises(ValueError):
            inspection_sheet([('bad', np.zeros((608, 1056, 3), np.uint8))], 1056, 608)
