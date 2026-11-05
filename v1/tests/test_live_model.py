import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from depthsbs_app.depth_backend import resolve_backend
from depthsbs_app.live_model import model_adapter


class LiveModelTests(unittest.TestCase):
    def test_capture_capability_and_binding_are_explicit(self):
        factory, prepare = Mock(), Mock()
        original = resolve_backend('da2-small',factory,prepare)
        small = model_adapter('da2-small')
        self.assertIs(small.bind_capture(original,False),original)
        bound = small.bind_capture(original,True)
        self.assertIs(bound.spec,original.spec)
        self.assertIs(bound.prepare,prepare)
        with patch('depthsbs_app.small_gpu_input.SmallGpuCaptureEngine') as engine:
            bound.engine_factory(None)
            engine.assert_called_once_with(None)
        factory.assert_not_called()
        for name in ('vda-small','ovda-small-c16'):
            adapter = model_adapter(name)
            with self.assertRaises(ValueError): adapter.bind_capture(original,True)
            with self.assertRaises(ValueError): adapter.renderer_factory(native=True,gpu_capture=True)
        self.assertTrue(model_adapter('da2-base').rowflow)
        self.assertFalse(small.rowflow)
        self.assertIs(model_adapter('da2-base').bind_capture(original,True),original)

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
        for (model,native,capture),name in expected.items():
            self.assertEqual(model_adapter(model).renderer_factory(native=native,gpu_capture=capture).__name__,name)
        for native in (False,True):
            self.assertIs(model_adapter('da2-base').renderer_factory(native=native,gpu_capture=True),
                          model_adapter('da2-base').renderer_factory(native=native,gpu_capture=False))

    def test_unknown_model_does_not_fall_back(self):
        for name in ('unknown',None,[]):
            with self.assertRaises(ValueError): model_adapter(name)

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
