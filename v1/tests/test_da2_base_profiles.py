import unittest
import cv2
import numpy as np
from pathlib import Path
from unittest.mock import patch
import tempfile
from depthsbs_app import da2_base


class ProfileTests(unittest.TestCase):
    def test_explicit_source_legacy_selection_does_not_change_native_default(self):
        with patch.object(da2_base,'profiles',return_value={(518,924):Path('wide')}),patch.object(Path,'is_file',return_value=True),patch.object(da2_base,'native_engine') as native,patch.object(da2_base,'legacy_engine') as legacy:
            for selected in (False,True):
                backend=da2_base.binding(Path('root'),Path('runtime'),device_depth=True,legacy_torch=selected)
                backend.engine_factory(None)
            self.assertEqual(native.call_count,1);self.assertEqual(legacy.call_count,1)
    def test_default_precision_and_no_fp32_folder_fallback(self):
        self.assertEqual(da2_base.PRECISION, 'fp16')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(strict=True)
            (root / '518x896-fp32').mkdir()
            with self.assertRaisesRegex(ValueError, 'FP16'):
                da2_base.profiles(root)
            (root / '518x896-fp16').mkdir()
            with patch.object(da2_base, 'checked_plan') as checked:
                self.assertEqual(da2_base.profiles(root), {(518,896): root/'518x896-fp16'})
                checked.assert_called_once_with(root/'518x896-fp16', (518,896))

    def test_resolution_mapping_and_fail_closed_selection(self):
        installed = {(518,896): Path('original'), (518,924): Path('wide')}
        with patch.object(da2_base, 'profiles', return_value=installed), patch.object(Path, 'is_file', return_value=True), patch.object(da2_base, 'native_engine') as engine:
            backend = da2_base.binding(Path('root'), Path('runtime'))
            self.assertEqual(backend.spec.runtime, 'tensorrt-fp16')
            with self.assertRaises(ValueError): backend.engine_factory(None)
            for w,h in ((1280,720),(1920,1080),(3840,2160)):
                backend.input_validator(dict(width=w,height=h))
                backend.engine_factory(None)
                self.assertEqual(engine.call_args.args[-1], (518,924))
            backend.input_validator(dict(width=1056,height=608))
            backend.engine_factory(None)
            self.assertEqual(engine.call_args.args[-1], (518,896))
            for w,h,shape in ((608,1056,(518,896)),(3440,1440,(518,924)),(1920,1200,(518,896))):
                backend.input_validator(dict(width=w,height=h))
                backend.engine_factory(None)
                self.assertEqual(engine.call_args.args[-1], shape)
            with self.assertRaises(ValueError): backend.input_validator(dict(width=4097,height=1440))
            with self.assertRaises(ValueError): backend.engine_factory(None)

    def test_geometry_and_content(self):
        for width,height,shape in ((160,90,(518,924)),(1056,608,(518,896)),
                                   (344,144,(518,924)),(160,100,(518,896)),
                                   (100,100,(518,896)),(91,161,(518,896)),(160,120,(518,896))):
            with self.subTest(size=(width,height)):
                frame = np.random.default_rng(7).integers(256,size=(height,width,3),dtype=np.uint8)
                chw = da2_base.preprocess(frame,shape)
                top,left,h,w = da2_base.content_rect(width,height,shape)
                if (width,height) in ((160,90),(1056,608)):
                    self.assertEqual((top,left,h,w),(0,0,*shape))
                else:
                    scale = min(shape[1]/width,shape[0]/height)
                    self.assertLessEqual(abs(w-width*scale),.5)
                    self.assertLessEqual(abs(h-height*scale),.5)
                ref = cv2.resize(frame/255.,(w,h),interpolation=cv2.INTER_CUBIC)
                ref = ((ref-[.485,.456,.406])/[.229,.224,.225]).astype(np.float32).transpose(2,0,1)
                np.testing.assert_array_equal(chw[:,top:top+h,left:left+w],ref)
                self.assertEqual(chw.shape,(3,*shape))
                np.testing.assert_array_equal(da2_base.depth_content(chw,width,height),ref)

    def test_corrupt_same_size_plan_rejected(self):
        with patch.object(Path,'resolve',lambda self,strict=True:self), patch.object(Path,'stat') as stat, patch.object(Path,'read_bytes',return_value=b'bad'):
            stat.return_value.st_size = da2_base.PLAN_BYTES
            with self.assertRaisesRegex(ValueError,'checksum'):
                da2_base.checked_plan(Path('artifact'))
