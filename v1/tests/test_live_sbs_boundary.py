import multiprocessing as mp
import unittest
import os
from unittest.mock import patch

from depthsbs_app.live_sbs import reset_reason, validate_strength, resolve_gpu_capture, resolve_renderer, resolve_history_policy
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
            self.assertTrue(resolve_gpu_capture({'kind':'window'}, 'vda-small', True))
            self.assertTrue(resolve_gpu_capture({'kind':'window'}, 'ovda-small-c16', True))
            for kind, model, gpu in (('monitor','da2-base',True), ('monitor','da2-small',True), ('window','da2-small',False), ('window','da2-base',False), ('monitor','vda-small',True), ('window','vda-small',False), ('monitor','ovda-small-c16',True), ('window','ovda-small-c16',False)):
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

    def test_vda_retains_only_one_short_skip_and_resets_on_cut_or_resize(self):
        shape = (1920, 1080)
        def reason(step, elapsed, *, cut=False, current=shape):
            return reset_reason(10, 10 + step, shape, current, cut,
                                previous_source_ns=500_000_000, source_ns=500_000_000 + elapsed,
                                vda_single_skip=True)
        self.assertIsNone(reason(2, 50_000_000))
        self.assertEqual(reason(2, 50_000_001), 'gap')
        self.assertEqual(reason(3, 40_000_000), 'gap')
        self.assertEqual(reason(2, 32_000_000, cut=True), 'cut')
        self.assertEqual(reason(2, 32_000_000, current=(1280, 720)), 'resize')
        self.assertEqual(reason(1, 100_000_001), 'gap')
        self.assertEqual(reason(2, -1), 'gap')
        self.assertEqual(reason(0, 20_000_000), 'gap')

    def test_vda_default_history_policy_and_diagnostic_overrides(self):
        with patch.dict(os.environ, {}, clear=True):
            policy=resolve_history_policy('vda-small')
        self.assertEqual(policy,dict(allow_coalescing=False,vda_single_skip=True,ovda_short_skip=False))
        self.assertEqual(resolve_history_policy('vda-small','vda-single-skip'),policy)
        self.assertFalse(any(resolve_history_policy('vda-small','legacy').values()))
        shape=(3840,2160)
        self.assertIsNone(reset_reason(10,12,shape,shape,False,
            previous_source_ns=1_000_000_000,source_ns=1_050_000_000,**policy))
        for sequence,elapsed in ((12,50_000_001),(13,33_333_333),(10,16_666_667),(9,16_666_667),
                                 (11,100_000_001),(11,0),(11,-1),(True,16_666_667),(12.0,33_333_333)):
            with self.subTest(sequence=sequence,elapsed=elapsed):
                self.assertEqual(reset_reason(10,sequence,shape,shape,False,
                    previous_source_ns=1_000_000_000,source_ns=1_000_000_000+elapsed,**policy),'gap')
        self.assertEqual(reset_reason(10,12,shape,shape,True,
            previous_source_ns=1_000_000_000,source_ns=1_033_333_333,**policy),'cut')
        self.assertEqual(reset_reason(10,12,shape,(1920,1080),False,
            previous_source_ns=1_000_000_000,source_ns=1_033_333_333,**policy),'resize')
        self.assertTrue(resolve_history_policy('da2-small','continuous')['allow_coalescing'])
        self.assertTrue(resolve_history_policy('ovda-small-c16','continuous')['ovda_short_skip'])
        with self.assertRaises(ValueError):resolve_history_policy('vda-small','invalid')

    def test_coalesced_da2_history_uses_source_time(self):
        shape = (3840, 2160)
        def reason(sequence=7, elapsed=33_333_333, cut=False, prior=1_000_000_000):
            return reset_reason(2, sequence, shape, shape, cut,
                                previous_source_ns=prior, source_ns=prior + elapsed,
                                allow_coalescing=True)
        self.assertIsNone(reason())
        self.assertIsNone(reason(elapsed=100_000_000))
        self.assertEqual(reason(cut=True), 'cut')
        for options in ({'sequence':2}, {'sequence':1}, {'elapsed':0},
                        {'elapsed':-1}, {'elapsed':100_000_001}, {'prior':0}):
            with self.subTest(options=options):
                self.assertEqual(reason(**options), 'gap')
        self.assertEqual(reset_reason(2, 7, shape, shape, False,
                                      allow_coalescing=True), 'gap')

    def test_history_capability_keeps_stateful_models_strict(self):
        from depthsbs_app.live_model import model_adapter
        for model in ('da2-small', 'da2-base'):
            self.assertTrue(model_adapter(model).coalesced_history)
        for model in ('vda-small', 'ovda-small-c16'):
            self.assertFalse(model_adapter(model).coalesced_history)
        self.assertTrue(model_adapter('ovda-small-c16').short_skip_history)
        for model in ('da2-small','da2-base','vda-small'):
            self.assertFalse(model_adapter(model).short_skip_history)
        self.assertTrue(model_adapter('vda-small').single_skip_history)
        for model in ('da2-small','da2-base','ovda-small-c16'):
            self.assertFalse(model_adapter(model).single_skip_history)

    def test_ovda_short_skip_has_count_and_source_time_bounds(self):
        shape=(1920,1080)
        def reason(step=2,elapsed=33_333_333,*,cut=False,current=shape,prior=1_000_000_000):
            return reset_reason(10,10+step,shape,current,cut,
                previous_source_ns=prior,source_ns=prior+elapsed,ovda_short_skip=True)
        self.assertIsNone(reason())
        self.assertIsNone(reason(elapsed=50_000_000))
        self.assertIsNone(reason(step=1,elapsed=16_666_667))
        for options in ({'step':3},{'step':0},{'step':-1},{'elapsed':0},
                        {'elapsed':-1},{'elapsed':50_000_001},{'step':1,'elapsed':50_000_001},
                        {'prior':0}):
            with self.subTest(options=options):self.assertEqual(reason(**options),'gap')
        self.assertEqual(reason(cut=True),'cut')
        self.assertEqual(reason(current=(1280,720)),'resize')
        self.assertEqual(reset_reason(1,2,shape,shape,False,ovda_short_skip=True),'gap')
        # Renderer coalescing and file inference cadence remain separate.
        self.assertEqual(reset_reason(10,12,shape,shape,False),'gap')
        for prior,now in ((True,100),(100,True),(100,101.0)):
            self.assertEqual(reset_reason(10,11,shape,shape,False,
                previous_source_ns=prior,source_ns=now,ovda_short_skip=True),'gap')

    def test_full_sbs_slot_capacity(self):
        mailbox = Mailbox.create(mp.get_context("spawn"), sbs=True)
        self.assertEqual(len(mailbox.pixels), MAX_BYTES * 2)

    def test_native_output_has_no_shared_color_buffer(self):
        mailbox = Mailbox.create(mp.get_context("spawn"), sbs=True, metadata_only=True)
        self.assertIsNone(mailbox.pixels)
        self.assertEqual(len(mailbox.meta), 12)


if __name__ == "__main__":
    unittest.main()
