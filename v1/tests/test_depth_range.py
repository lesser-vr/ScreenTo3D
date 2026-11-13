import unittest
import numpy as np
from screento3d_app.depth_range import DepthRangeTracker,RangeParameters,settle_bounds


class DepthRangeTests(unittest.TestCase):
    def setUp(self):
        self.raw=np.tile(np.linspace(.1,.9,256,dtype=np.float32),(144,1))
        self.rgb=np.full((144,256,3),120,np.uint8)

    def update(self,tracker,raw,index,**kwargs):
        return tracker.update(raw,self.rgb,self.rgb,np.quantile(raw,[.02,.98]).astype(np.float32),
                              1_000_000_000+index*16_666_667,**kwargs)

    def test_reject_invalid_parameters(self):
        for args in (dict(deadband=-.01),dict(deadband=.06),dict(deadband=True),dict(expand_seconds=0),
                     dict(expand_seconds=1,contract_seconds=.5),dict(contract_seconds=float('nan'))):
            with self.assertRaises(ValueError):RangeParameters(**args)

    def test_small_tail_changes_leave_middle_depth_scale_fixed(self):
        tracker=DepthRangeTracker();initial=self.update(tracker,self.raw,0)
        changed=self.raw.copy();changed[:,:12]-=.01;changed[:,-12:]+=.01
        bounds=self.update(tracker,changed,1)
        np.testing.assert_allclose(bounds,initial,atol=1e-7)

    def test_raw_anchor_transport_tracks_model_affine_drift(self):
        tracker=DepthRangeTracker();initial=self.update(tracker,self.raw,0)
        for i in range(1,40):
            scale=1+i*.002;offset=i*.0003
            bounds=self.update(tracker,self.raw*scale+offset,i)
            np.testing.assert_allclose(bounds,np.array(initial)*scale+offset,atol=2e-7)

    def test_changed_rgb_rejects_affine_fit(self):
        tracker=DepthRangeTracker();initial=self.update(tracker,self.raw,0)
        shifted=self.raw+.05
        actual=tracker.update(shifted,self.rgb+20,self.rgb,np.array(initial)+.05,1_016_666_667)
        expected=settle_bounds(initial,np.array(initial)+.05,16_666_667/1e9,RangeParameters())
        np.testing.assert_allclose(actual,expected)

    def test_range_expansion_is_fast_contraction_is_time_based(self):
        params=RangeParameters(deadband=0)
        for hz in (30,60,120):
            bounds=(0.,1.)
            for _ in range(hz):bounds=settle_bounds(bounds,(-1.,2.),1/hz,params)
            np.testing.assert_allclose(bounds,(-1.,2.),atol=1e-8)
            for _ in range(hz):bounds=settle_bounds(bounds,(0.,1.),1/hz,params)
            np.testing.assert_allclose(bounds,(-np.exp(-2),1+np.exp(-2)),atol=1e-8)

    def test_cut_clock_discontinuity_and_resize_adopt_new_range(self):
        for reason in ('cut','clock','size'):
            tracker=DepthRangeTracker();self.update(tracker,self.raw,0)
            raw=np.full((144,256) if reason!='size' else (72,128),.7,np.float32)
            rgb=np.full((*raw.shape,3),120,np.uint8)
            expected=tuple(np.quantile(raw,[.02,.98]))
            actual=tracker.update(raw,rgb,self.rgb,expected,1_000_000_000 if reason=='clock' else 1_016_666_667,reset=reason=='cut')
            self.assertEqual(actual,expected)

    def test_invalid_input_fails_before_advancing_clock(self):
        tracker=DepthRangeTracker();bad=self.raw.copy();bad[0,0]=np.nan
        with self.assertRaises(ValueError):self.update(tracker,bad,0)
        self.assertIsNone(tracker.clock.source_ns)

    def test_cpu_live_uses_tracker_and_resets_pixel_history_on_clock_change(self):
        from dataclasses import replace
        from screento3d_app.config import MODES
        from screento3d_app.live_policy import resolve_live
        from screento3d_app.pipeline import StereoSynthesizer
        policy=replace(resolve_live('video-quality',.5),temporal_depth_alpha=.5,stabilize_depth_range=True)
        def pair(frame,depth,shift,**kwargs):return frame.copy(),frame.copy()
        synth=StereoSynthesizer(256,144,policy,paired_projection=pair)
        synth.source_ns=1_000_000_000;synth.render(self.rgb,self.raw[None])
        synth.source_ns=1_000_000_000;synth.render(self.rgb,np.full((1,144,256),.7,np.float32))
        self.assertEqual(synth.low,synth.high)
        np.testing.assert_array_equal(synth.smoothed_depth,0)
        self.assertTrue(all(not p.stabilize_depth_range for p in MODES.values()))


if __name__=='__main__':unittest.main()
