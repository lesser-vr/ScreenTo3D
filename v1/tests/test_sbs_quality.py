import unittest
import cv2
import numpy as np
from depthsbs_app.sbs_quality import masked_error,temporal_disparity,edge_reprojection,step_response,unpack_half_tb,motion_map


class SbsQualityTests(unittest.TestCase):
    def test_empty_regions_are_unavailable_not_perfect(self):
        rgb=np.zeros((16,32,3),np.uint8)
        self.assertIsNone(masked_error(rgb,rgb,np.zeros((16,32),bool))['mae'])
        with self.assertRaises(ValueError):masked_error(rgb,np.zeros((8,8,3)),np.ones((16,32),bool))

    def test_motion_alignment_preserves_disparity_units_and_drift(self):
        yy,xx=np.indices((24,48),dtype=np.float32)
        old=xx*.3;current=(xx-2)*.3
        mask=(xx>4)&(xx<44)&(yy>2)&(yy<20)
        maps=(xx-2,yy,mask,mask)
        result=temporal_disparity(old,current,maps)
        self.assertLess(result['all']['rmse_px'],1e-6)
        self.assertAlmostEqual(temporal_disparity(old,current+2,maps)['all']['rmse_px'],2,places=5)
        with self.assertRaises(ValueError):temporal_disparity(old,current*np.nan,maps)

    def test_zero_disparity_reprojection_and_nonzero_error(self):
        rgb=np.random.default_rng(3).integers(0,220,(24,64,3),np.uint8)
        rows=edge_reprojection(rgb,[rgb,rgb],np.zeros((24,64),np.float32))
        self.assertTrue(all(row['mae']==0 and row['pixels']>0 for row in rows))
        rows=edge_reprojection(rgb,[rgb+10,rgb+10],np.zeros((24,64),np.float32))
        self.assertTrue(all(abs(row['mae']-10)<.001 for row in rows))

    def test_response_cannot_reward_frozen_depth(self):
        self.assertEqual(step_response([1]*10,0,1)['t90_ms'],0)
        frozen=step_response([0]*30,0,1)
        self.assertIsNone(frozen['t90_ms']);self.assertEqual(frozen['gain'],0)
        self.assertEqual(step_response([0,0,1,1,1,1,1],0,1)['updates_to_90'],3)
        self.assertIsNone(step_response([.4]*10,.4,.41)['gain'])
        response=step_response([1]*5+[2]+[1]*6,0,1)
        self.assertEqual(response['first_90_ms'],0)
        self.assertEqual(response['updates_to_90'],7)

    def test_half_tb_sampling_control_matches_source_grid(self):
        from depthsbs_app.stereo_layout import pack
        rgb=np.random.default_rng(5).integers(0,256,(128,256,3),np.uint8)
        packed=pack(np.concatenate((rgb,rgb),axis=1),'half-tb')
        expected=cv2.resize(rgb,(64,32),interpolation=cv2.INTER_AREA)
        for eye in unpack_half_tb(packed,64,32):
            self.assertLessEqual(int(np.max(np.abs(eye.astype(int)-expected.astype(int)))),1)

    def test_rgb_flow_finds_known_translation(self):
        rgb=np.random.default_rng(8).integers(0,256,(128,240,3),np.uint8)
        current=cv2.warpAffine(rgb,np.float32([[1,0,2],[0,1,0]]),(240,128),borderMode=cv2.BORDER_REFLECT)
        yy,xx=np.indices((128,240),dtype=np.float32)
        maps=motion_map(rgb,current)
        result=temporal_disparity(xx*.1,(xx-2)*.1,maps)
        self.assertGreater(result['valid_fraction'],.5)
        self.assertLess(result['all']['rmse_px'],.05)


if __name__=='__main__':unittest.main()
