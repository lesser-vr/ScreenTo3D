import unittest
from unittest.mock import patch
import io
from pathlib import Path
import tempfile
import zipfile
import numpy as np
from depthsbs_app.spring_quality import fit_affine,align,spatial_error,temporal_geometry,temporal_error
from prepare_spring_subset import extract_member,get_range


class SpringQualityTests(unittest.TestCase):
    def test_fixed_calibration_preserves_later_drift(self):
        x=np.linspace(1,10,1000,dtype=np.float32)
        fit=fit_affine([x],[x*3+7])
        prediction=align(x.reshape(20,50),fit)
        truth=(x*3+7).reshape(20,50)
        self.assertLess(spatial_error(prediction,truth)['all']['rmse_px'],1e-5)
        self.assertAlmostEqual(spatial_error(prediction+2,truth)['all']['mae_px'],2,places=5)
        with self.assertRaises(ValueError):fit_affine([x*0],[x])

    def test_true_depth_change_is_not_flicker_and_frozen_depth_loses(self):
        yy,xx=np.indices((32,64),dtype=np.float32)
        old=xx*.2+5;new=(xx-2)*.2+7
        flow=np.zeros((32,64,2),np.float32);flow[:,:,0]=2
        # Future disparity at the old material point is old + 2.
        geom=temporal_geometry(old,new,old+2,flow)
        correct=temporal_error(old,new,geom)
        self.assertGreater(correct['valid_fraction'],.5)
        self.assertLess(correct['all']['rmse_px'],1e-5)
        frozen=temporal_error(old,new-2,geom)
        self.assertAlmostEqual(frozen['all']['rmse_px'],2,places=5)
        self.assertAlmostEqual(correct['frozen_control']['rmse_px'],2,places=5)

    def test_visibility_and_invalid_truth_are_not_prediction_masks(self):
        truth=np.ones((24,48),np.float32)*5
        target=truth.copy();target[:,15:25]=10;target[0,0]=np.nan
        geom=temporal_geometry(truth,truth,target,np.zeros((24,48,2),np.float32))
        self.assertFalse(geom[2][:,16:24].any())
        self.assertIsNone(temporal_error(truth,truth,(geom[0],geom[1],geom[2]&False,geom[3],geom[4]))['all']['mae_px'])
        with self.assertRaises(ValueError):spatial_error(truth*np.nan,truth)

    def test_partial_archive_extraction_checks_crc_and_resume(self):
        buffer=io.BytesIO();name='spring/train/0001/frame_left/frame_left_0001.png'
        with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED) as archive:archive.writestr(name,b'sample'*100)
        data=buffer.getvalue()
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            item=archive.getinfo(name)
            member=dict(name=name,offset=item.header_offset,size=item.file_size,compressed=item.compress_size,
                method=item.compress_type,crc=item.CRC,flags=item.flag_bits)
        record=dict(id=1,filename='test.zip',filesize=len(data))
        with tempfile.TemporaryDirectory() as directory:
            with patch('prepare_spring_subset.get_range',side_effect=lambda url,start,length,total:data[start:start+length]):
                first=extract_member(record,member,Path(directory))
            with patch('prepare_spring_subset.get_range',side_effect=AssertionError('Resume must verify local member')):
                self.assertEqual(first,extract_member(record,member,Path(directory)))
            with patch('prepare_spring_subset.get_range',side_effect=lambda url,start,length,total:data[start:start+length]):
                with self.assertRaisesRegex(ValueError,'CRC'):extract_member(record,dict(member,crc=0),Path(directory))
            for bad in ('spring/train/../../escape','spring/train/C:/escape'):
                with self.assertRaises(ValueError):extract_member(record,dict(member,name=bad),Path(directory))

    def test_range_rejects_full_archive_response_before_reading(self):
        class FullResponse:
            status=200;headers={}
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):raise AssertionError('Must not read a full archive')
        with patch('urllib.request.urlopen',return_value=FullResponse()):
            with self.assertRaisesRegex(ValueError,'bounded range'):get_range('https://example.invalid/',0,10,100)


if __name__=='__main__':unittest.main()
