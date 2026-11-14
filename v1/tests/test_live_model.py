import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from screento3d_app.depth_backend import resolve_backend
from screento3d_app.live_model import model_adapter


class LiveModelTests(unittest.TestCase):
    def test_capture_capability_and_binding_are_explicit(self):
        factory, prepare = Mock(), Mock()
        original = resolve_backend('da2-small',factory,prepare)
        small = model_adapter('da2-small')
        self.assertIs(small.bind_capture(original,False),original)
        bound = small.bind_capture(original,True)
        self.assertIs(bound.spec,original.spec)
        self.assertIs(bound.prepare,prepare)
        with patch('screento3d_app.native_small.NativeSmallEngine') as engine:
            bound.engine_factory(None)
            engine.assert_called_once_with(None)
        factory.assert_not_called()
        adapter = model_adapter('ovda-small-c16')
        self.assertIs(adapter.bind_capture(original,True),original)
        self.assertTrue(adapter.gpu_capture)
        self.assertFalse(adapter.coalesced_history)
        self.assertTrue(model_adapter('da2-base').rowflow)
        self.assertFalse(small.rowflow)
        self.assertIs(model_adapter('da2-base').bind_capture(original,True),original)
        self.assertIs(model_adapter('vda-small').bind_capture(original,True),original)

    def test_renderer_matrix_keeps_existing_consumers(self):
        expected = {
            ('da2-small',False,False):'LiveGpuCandidate',
            ('da2-small',True,False):'LiveGpuTexture',
            ('da2-small',False,True):'LiveSmallGpuInput',
            ('da2-small',True,True):'LiveSmallGpuInputTexture',
        }
        for model in ('da2-base','vda-small','ovda-small-c16'):
            for native in (False,True):
                expected[model,native,False] = 'LiveSourceGpuTexture' if native else 'LiveSourceGpuCandidate'
                expected[model,native,True] = 'LiveSourceGpuTexture' if native else 'LiveSourceGpuCandidate'
        for (model,native,capture),name in expected.items():
            self.assertEqual(model_adapter(model).renderer_factory(native=native,gpu_capture=capture).__name__,name)
        for native in (False,True):
            self.assertIs(model_adapter('da2-base').renderer_factory(native=native,gpu_capture=True),
                          model_adapter('da2-base').renderer_factory(native=native,gpu_capture=False))

    def test_unknown_model_does_not_fall_back(self):
        for name in ('unknown',None,[]):
            with self.assertRaises(ValueError): model_adapter(name)

    def test_ovda_pixel_ema_is_independent_of_range_and_other_models(self):
        from dataclasses import asdict,replace
        from screento3d_app.live_policy import resolve_live,LIVE_MODES
        original=resolve_live('video-quality',.5)
        updated=model_adapter('ovda-small-c16').apply_live_policy(original)
        self.assertEqual(updated.temporal_alpha,.18)
        self.assertEqual(updated.temporal_depth_alpha,.5)
        self.assertTrue(updated.stabilize_depth_range)
        self.assertEqual(asdict(replace(updated,temporal_depth_alpha=None,stabilize_depth_range=False)),asdict(original))
        for name in ('da2-small','da2-base','vda-small'):
            self.assertEqual(model_adapter(name).apply_live_policy(original),original)
        described=LIVE_MODES['video-quality'].describe(.5,'ovda-small-c16')['stereo']
        self.assertEqual(described['temporal_depth_alpha'],.5)
        self.assertEqual(described['temporal_alpha'],.18)
        self.assertTrue(described['stabilize_depth_range'])

    def test_host_transfer_accounting_keeps_model_contract(self):
        frame,depth=SimpleNamespace(shape=(1080,1920,3)),SimpleNamespace(nbytes=1080*1920*4)
        small=SimpleNamespace(input_bytes=3*518*518*4,output_bytes=518*518*4)
        self.assertEqual(model_adapter('da2-small').host_io_bytes(small,frame,depth),
                         (small.input_bytes,small.output_bytes))
        for name,engine,expected in (
            ('da2-base',SimpleNamespace(shape=(518,924)),3*518*924*4),
            ('vda-small',SimpleNamespace(input_shape=(1,1,3,518,924)),3*518*924*4)):
            self.assertEqual(model_adapter(name).host_io_bytes(engine,frame,depth),(expected,depth.nbytes))


if __name__ == '__main__': unittest.main()
