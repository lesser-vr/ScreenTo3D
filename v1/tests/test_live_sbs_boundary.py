import multiprocessing as mp
import unittest
import os
from unittest.mock import patch

from depthsbs_app.live_sbs import reset_reason, validate_strength, resolve_gpu_capture, resolve_renderer
from depthsbs_app.capture_mailbox import Mailbox, MAX_BYTES


class LiveSbsBoundaryTests(unittest.TestCase):
    def test_renderer_is_explicit_and_snapshot_is_stable(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_renderer('da2-base', True), 'cuda')
        with patch.dict(os.environ, {'DEPTHSBS_STEREO_RENDERER':'rowflow-sym'}):
            self.assertEqual(resolve_renderer('da2-base', True), 'rowflow-sym')
            self.assertEqual(resolve_renderer('da2-small', False, setting='cuda'), 'cuda')
            for model,gpu,strength in [('da2-small',True,1),('da2-base',False,1),('da2-base',True,2),('da2-base',True,float('nan'))]:
                with self.assertRaises(ValueError):resolve_renderer(model,gpu,strength)
        with self.assertRaises(ValueError):resolve_renderer('da2-base',True,setting='unknown')

    def test_gpu_capture_selection_preserves_other_paths(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(resolve_gpu_capture({'kind':'window'}, 'da2-base', True))
            self.assertTrue(resolve_gpu_capture({'kind':'window'}, 'da2-small', True))
            for kind, model, gpu in (('monitor','da2-base',True), ('monitor','da2-small',True), ('window','da2-small',False), ('window','da2-base',False), ('window','vda-small',True)):
                self.assertFalse(resolve_gpu_capture({'kind':kind}, model, gpu))
        with patch.dict(os.environ, {'DEPTHSBS_GPU_CAPTURE':'0'}):
            self.assertFalse(resolve_gpu_capture({'kind':'window'}, 'da2-base', True))
        with patch.dict(os.environ, {'DEPTHSBS_GPU_CAPTURE':'invalid'}):
            with self.assertRaises(ValueError):
                resolve_gpu_capture({'kind':'window'}, 'da2-base', True)

    def test_resets(self):
        shape = (720, 480)
        self.assertEqual(reset_reason(None, 1, None, shape, False), "start")
        self.assertEqual(reset_reason(1, 3, shape, shape, False), "gap")
        self.assertEqual(reset_reason(1, 2, shape, (600, 420), False), "resize")
        self.assertEqual(reset_reason(1, 2, shape, shape, True), "cut")
        self.assertIsNone(reset_reason(1, 2, shape, shape, False))

    def test_strength_boundary(self):
        for value in (0, -1, 2.1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                validate_strength(value)
        self.assertEqual(validate_strength(1.25), 1.25)

    def test_full_sbs_slot_capacity(self):
        mailbox = Mailbox.create(mp.get_context("spawn"), sbs=True)
        self.assertEqual(len(mailbox.pixels), MAX_BYTES * 2)

    def test_native_output_has_no_shared_color_buffer(self):
        mailbox = Mailbox.create(mp.get_context("spawn"), sbs=True, metadata_only=True)
        self.assertIsNone(mailbox.pixels)
        self.assertEqual(len(mailbox.meta), 12)


if __name__ == "__main__":
    unittest.main()
