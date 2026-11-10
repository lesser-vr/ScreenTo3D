import unittest
import numpy as np
from depthsbs_app.sbs_rgb_quality import rgb_metrics,half_tb_reference,restored_eyes,reference_eyes
from sbs_rgb_fixture import render,BASELINE,CONVERGENCE_Z


class SbsRgbQualityTests(unittest.TestCase):
    def test_rgb_identity_offset_and_no_measurement(self):
        rgb=np.random.default_rng(9).integers(10,230,(48,64,3),np.uint8);mask=np.ones((48,64),bool)
        same=rgb_metrics(rgb,rgb,mask)
        self.assertTrue(same['perfect']);self.assertAlmostEqual(same['ssim'],1,places=5)
        changed=rgb_metrics(rgb+10,rgb,mask)
        self.assertAlmostEqual(changed['mse'],100,places=4)
        self.assertAlmostEqual(changed['psnr_db'],28.1308036087,places=5)
        self.assertLess(changed['ssim'],1)
        self.assertIsNone(rgb_metrics(rgb,rgb,mask&False)['mae'])

    def test_half_reference_and_native_sampling_contract(self):
        rgb=np.random.default_rng(10).integers(0,256,(48,64,3),np.uint8)
        expected=reference_eyes([rgb,rgb],'half-tb')
        packed=np.concatenate(half_tb_reference([rgb,rgb]),axis=0)
        bgra=np.concatenate((packed,np.full((*packed.shape[:2],1),255,np.uint8)),axis=2)
        for a,b in zip(expected,restored_eyes(bgra,'half-tb',64,48)):np.testing.assert_array_equal(a,b)
        with self.assertRaises(ValueError):restored_eyes(bgra[:,:,:3],'half-tb',64,48)

    def test_independent_ray_camera_geometry(self):
        _,z,_=render('room',0,width=160,height=90)
        self.assertTrue(np.isfinite(z).all());self.assertGreater(float(z.min()),0)
        # A point at Z has xL-xR = f B (1/Z - 1/Z0), not the opposite sign.
        f=.9*160;world_x=.2;depth=2.5
        def project(camera):return f*((world_x-camera)/depth+camera/CONVERGENCE_Z)+80-.5
        measured=project(-BASELINE/2)-project(BASELINE/2)
        self.assertAlmostEqual(measured,f*BASELINE*(1/depth-1/CONVERGENCE_Z),places=7)
        self.assertGreater(measured,0)


if __name__=='__main__':unittest.main()
