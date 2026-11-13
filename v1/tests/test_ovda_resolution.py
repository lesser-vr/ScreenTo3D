import unittest
from screento3d_app import ovda
from screento3d_app.ovda_geometry import CANVASES,content_rect,select_profile


class OvdaResolutionTests(unittest.TestCase):
    def test_normal_profiles_never_select_trial_resolution(self):
        self.assertEqual(set(ovda.PROFILES),{(518,924)})
        for size in ((1920,1080),(3840,2160),(3440,1440),(1080,1920),(1024,1024)):
            self.assertIn(ovda.input_shape(dict(width=size[0],height=size[1])),CANVASES)

    def test_explicit_low_canvas_preserves_content_aspect_and_bounds(self):
        for w,h in ((1920,1080),(3840,2160),(3440,1440),(1080,1920),(1024,1024),(16,2160)):
            shape=select_profile(w,h,((392,700),))
            self.assertEqual(shape,(392,700))
            top,left,rh,rw=content_rect(w,h,shape)
            self.assertGreaterEqual(top,0);self.assertGreaterEqual(left,0)
            self.assertLessEqual(top+rh,392);self.assertLessEqual(left+rw,700)
            self.assertLessEqual(abs(rw/w-rh/h),max(1/w,1/h))

    def test_unexported_canvases_are_rejected(self):
        for shape in ((392,686),(400,700),(518,518),(392,True)):
            with self.assertRaises(ValueError):content_rect(1920,1080,shape)
            with self.assertRaises(ValueError):select_profile(1920,1080,(shape,))


if __name__=='__main__':unittest.main()
