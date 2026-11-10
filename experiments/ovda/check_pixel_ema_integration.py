# oVDA postprocess integration checks, NC-SA-UHDV1.0; see LICENSE/README.md.
"""Product routing, unchanged-range isolation and borrowed-context failure cleanup."""
import argparse
import json
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch
import numpy as np
from depthsbs_app import ovda
from depthsbs_app.live_model import model_adapter
from depthsbs_app.live_policy import resolve_live
from depthsbs_app.live_source_gpu_texture import LiveSourceGpuTexture
from evaluate_pixel_ema import FixtureOwner,readers,render_all


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    ovda.runtime_class(True)
    from _depthsbs_ovda import postprocess
    w,h=512,288;engine=FixtureOwner(w,h)
    policy=replace(resolve_live('video-quality',.5),depth_backend='ovda-small-c16',stereo_layout='half-tb')
    # Isolate pixel EMA even after live oVDA adopts a different range tracker.
    product=replace(model_adapter('ovda-small-c16').apply_live_policy(policy),stabilize_depth_range=False)
    report=dict(rejections=[],frames=0)
    posts={}
    def rejected(name,error,operation):
        try:operation()
        except error:report['rejections'].append(name)
        else:raise AssertionError('Missing rejection: '+name)
    try:
        for alpha in (0,-.1,1.1,float('nan'),float('inf'),True):
            rejected('invalid alpha '+str(alpha),ValueError,lambda:postprocess.OvdaPostBridge(None,alpha))
        closed=[];original=LiveSourceGpuTexture.close
        def closed_check(value):
            original(value);closed.append(not value.handle.value and value.pool is None)
        with patch.object(postprocess,'DLL_SHA256','0'*64),patch.object(LiveSourceGpuTexture,'close',closed_check):
            rejected('DLL checksum cleanup',ValueError,lambda:LiveSourceGpuTexture(w,h,product,engine,diagnostic=True))
        assert closed==[True]
        posts['legacy']=LiveSourceGpuTexture(w,h,policy,engine,diagnostic=True)
        posts['0.18']=LiveSourceGpuTexture(w,h,replace(product,temporal_depth_alpha=.18),engine,diagnostic=True)
        posts['product']=LiveSourceGpuTexture(w,h,product,engine,diagnostic=True)
        posts['explicit']=postprocess.OvdaGpuTexture(w,h,policy,engine,diagnostic=True,pixel_alpha=.5)
        buffers={name:readers(post,w,h) for name,post in posts.items()}
        rgb=np.full((h,w,3),120,np.uint8)
        ramp=np.tile(np.linspace(.1,.9,w,dtype=np.float32),(h,1))
        for i in range(48):
            raw=ramp.copy();raw[90:198,200:312]=.45 if i<24 else .49
            if i==40:
                for post in posts.values():post.reset()
            outputs=render_all(engine,posts,rgb,engine.token(raw),i,buffers,w,h)
            np.testing.assert_array_equal(outputs['product'],outputs['explicit'])
            np.testing.assert_array_equal(buffers['product'][1],buffers['explicit'][1])
            report['frames']+=1
        assert posts['product']._post_override.pixel_alpha==.5
        assert posts['product'].policy.temporal_alpha==.18
        report['passed']=True
    finally:
        for post in posts.values():post.close()
        engine.close()
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2))
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
