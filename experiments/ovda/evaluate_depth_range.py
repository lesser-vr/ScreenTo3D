# oVDA range comparison, NC-SA-UHDV1.0; see LICENSE/README.md.
"""Causal range comparison: fixed .5 pixel EMA, c16 history, same raw depth.

Require exact old/new legacy parity; CPU/GPU range agreement; reduced synthetic
tail jitter and affine drift; immediate reset; natural low-motion eye-shift RMS
increase <=.1 pixel at 4K/strength .5. Added clip audit: excess loss >.05 of
current P2/P98 span may grow by at most .5 percentage point. These are proxies,
not depth ground truth. Public frames are evaluated at a declared 60 Hz clock.
"""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
import cv2
import numpy as np
import torch
from depthsbs_app import ovda
from depthsbs_app.depth_range import DepthRangeTracker,RangeParameters
from depthsbs_app.desktop_jobs import ROOT
from depthsbs_app.live_policy import resolve_live
from depthsbs_app.gpu_frame import GpuFrame
from depthsbs_app.ovda_geometry import select_profile
from depthsbs_app.stereo_layout import dimensions
from evaluate_pixel_ema import FixtureOwner,readers
from public_test_media import CORPUS

OLD=('out/ovda-postprocess/ovda_postprocess.dll','da3a065477429ce271382739a83bccea0d52dfd6222fefeafbc55d10f35c69c6')
NEW=('out/ovda-postprocess-range/ovda_postprocess.dll','b4873fc3b2b479a825526b1a3fd397e4b255ca1ecc3b3ddbfeec442763372629')


def make_posts(engine,w,h,product=False):
    from _depthsbs_ovda import postprocess as module
    from depthsbs_app.live_model import model_adapter
    from depthsbs_app.live_source_gpu_texture import LiveSourceGpuTexture
    policy=replace(resolve_live('video-quality',.5),stereo_layout='half-tb',depth_backend='ovda-small-c16')
    posts={}
    try:
        for name,(path,digest),parameters in (('legacy',OLD,None),('parity',NEW,None),('stable',NEW,RangeParameters())):
            with patch.object(module,'DLL_PATH',ROOT/path),patch.object(module,'DLL_SHA256',digest):
                posts[name]=module.OvdaGpuTexture(w,h,policy,engine,diagnostic=True,pixel_alpha=.5,range_parameters=parameters)
        if product:
            posts['product']=LiveSourceGpuTexture(w,h,model_adapter('ovda-small-c16').apply_live_policy(policy),engine,diagnostic=True)
        return posts,{name:readers(post,w,h) for name,post in posts.items()}
    except BaseException:
        for post in posts.values():post.close()
        raise


def render_all(engine,posts,frame,token,index,buffers,w,h):
    complete=engine.complete_device;outputs={}
    try:
        with patch.object(engine,'complete_device',lambda value:value.validate()):
            for name,post in posts.items():
                post.source_ns=1_000_000_000+index*16_666_667
                post.slot=index%2;slot=post.render(frame,token)
                ow,oh=dimensions(w,h,'half-tb');rgba=np.empty((oh,ow,4),np.uint8)
                post.pool.check(post.pool.dll.live_pool_readback(post.pool.handle,slot,rgba.ctypes.data))
                norm,smooth,bounds,shift=buffers[name]
                post._check(post.dll.live_snapshot(post.handle,norm.ctypes.data,smooth.ctypes.data,bounds.ctypes.data))
                post._check(post.dll.live_shift_snapshot(post.handle,shift.ctypes.data))
                assert all(np.isfinite(a).all() for a in buffers[name])
                assert bounds[1]>=bounds[0]
                outputs[name]=rgba
    finally:complete(token)
    for actual,expected in zip(buffers['parity'],buffers['legacy']):np.testing.assert_array_equal(actual,expected)
    np.testing.assert_array_equal(outputs['parity'],outputs['legacy'])
    if 'product' in posts:
        for actual,expected in zip(buffers['product'],buffers['stable']):np.testing.assert_array_equal(actual,expected)
        np.testing.assert_array_equal(outputs['product'],outputs['stable'])
    return outputs


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--synthetic-only',action='store_true')
    parser.add_argument('--product',action='store_true')
    parser.add_argument('--clip-audit',action='store_true',help='Extra saturation-loss audit: 720p ParkingGarage and 4K OfficeWalk')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    cls=ovda.runtime_class(True)
    report=dict(contract=__doc__,dlls=dict(old=OLD,new=NEW),synthetic={},natural=[],sources={})
    def save():(args.output/'report.json').write_text(json.dumps(report,indent=2))
    try:
        w,h=512,288;engine=FixtureOwner(w,h);posts={}
        try:
            posts,buffers=make_posts(engine,w,h,args.product)
            ramp=np.tile(np.linspace(.1,.9,w,dtype=np.float32),(h,1))
            for case in (() if args.clip_audit else ('tail-jitter','affine-drift','new-near-far','flat-cut')):
                for post in posts.values():post.reset()
                tracker=DepthRangeTracker();previous=None
                rows={name:[] for name in posts};oracle_max=0.
                for i in range(180):
                    rgb=np.full((h,w,3),120,np.uint8);raw=ramp.copy()
                    if case=='tail-jitter':
                        if i>=30:
                            raw[:,:24]+=.012*np.sin(i*1.9);raw[:,-24:]+=.012*np.cos(i*1.9)
                        rgb[:,:24]=100+(i%2)*20;rgb[:,-24:]=100+(i%2)*20
                    elif case=='affine-drift':raw=raw*np.float32(1+i*.002)+np.float32(i*.0002)
                    elif case=='new-near-far' and 30<=i<90:
                        raw[:,:40]=-.15;raw[:,-40:]=1.2;rgb[:,:40]=60;rgb[:,-40:]=200
                    elif case=='flat-cut':
                        if i>=60:raw[:]=.7
                        if i==60:
                            for post in posts.values():post.reset()
                    render_all(engine,posts,rgb,engine.token(raw),i,buffers,w,h)
                    target=np.quantile(raw,[.02,.98]).astype(np.float32)
                    expected=tracker.update(raw,rgb,previous,target,1_000_000_000+i*16_666_667,reset=i==0 or (case=='flat-cut' and i==60))
                    delta=float(np.max(np.abs(buffers['stable'][2]-expected)));oracle_max=max(oracle_max,delta)
                    np.testing.assert_allclose(buffers['stable'][2],expected,atol=2e-6,rtol=2e-6)
                    for name in posts:
                        rows[name].append(dict(bounds=buffers[name][2].tolist(),center=float(buffers[name][1][80:208,200:312].mean())))
                    previous=rgb
                result=dict(cpu_gpu_max_error=oracle_max,frames=180,series=rows)
                report['synthetic'][case]=result;save()
                if case in ('tail-jitter','affine-drift'):
                    result['center_std']={name:float(np.std([r['center'] for r in values[20:]])) for name,values in rows.items()}
                    assert result['center_std']['stable']<result['center_std']['legacy']*.6,result['center_std']
                if case=='new-near-far':
                    target=np.quantile(ramp,[.02,.98]).astype(np.float32)
                    result['final_bounds']=rows['stable'][-1]['bounds']
                    assert max(abs(np.array(result['final_bounds'])-target))<.025
                    opened=np.array(rows['stable'][39]['bounds'])
                    assert max(abs(opened-[-.15,1.2]))<.06
                if case=='flat-cut':assert rows['stable'][60]['bounds']==[float(np.float32(.7))]*2
                report['synthetic'][case]=result;save()
                print(json.dumps(dict(case=case,oracle_max=oracle_max,center_std=result.get('center_std'))),flush=True)
        finally:
            for post in posts.values():
                post.close()
                bridge=getattr(post,'bridge',getattr(post,'_post_override',None))
                if bridge is not None:assert bridge.anchors is None
            engine.close()
        if not args.synthetic_only:
            profiles=ovda.profiles(ROOT/'out/ovda-local')
            sizes=((1280,720,180),(3840,2160,90)) if args.clip_audit else ((1280,720,180),(720,1280,120),(3840,2160,90))
            for w,h,count in sizes:
                shape=select_profile(w,h,profiles);engine=cls(directory=profiles[shape],profile=shape);posts={}
                try:
                    posts,buffers=make_posts(engine,w,h,args.product)
                    clips=(('ParkingGarage',) if w==1280 else ('OfficeWalk',)) if args.clip_audit else ('FloorballGame','OfficeWalk','ParkingGarage')
                    for clip in clips:
                        engine.reset('scene_cut')
                        for post in posts.values():post.reset()
                        path=CORPUS/(clip+'.mp4');digest=hashlib.sha256(path.read_bytes()).hexdigest()
                        assert digest==json.loads(path.with_suffix('.json').read_text())['sha256']
                        report['sources'][clip]=digest
                        cap=cv2.VideoCapture(str(path));previous=None;shifts={}
                        data={name:dict(square=0.,n=0,clipped=0,severe=0,pixels=0) for name in posts}
                        try:
                            for i in range(count):
                                ok,bgr=cap.read();assert ok
                                rgb=np.ascontiguousarray(cv2.resize(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB),(w,h)))
                                with torch.cuda.stream(engine.stream):frame=GpuFrame(torch.from_numpy(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGRA)).to(engine.device),engine)
                                token=engine.infer_device(frame)
                                render_all(engine,posts,frame,token,i,buffers,w,h)
                                if previous is not None and i>=8:
                                    # Diagnostic-only raw readback quantifies information lost to
                                    # saturation beyond each frame's own P2/P98 clipping contract.
                                    with torch.cuda.stream(engine.stream):raw=token.tensor[0].cpu().numpy()
                                    lo,hi=np.quantile(raw,[.02,.98]);reference=np.clip((raw-lo)/max(hi-lo,1e-6),0,1)
                                    stable=np.max(np.abs(rgb.astype(np.int16)-previous.astype(np.int16)),axis=2)<=2
                                    stable=cv2.erode(stable.astype(np.uint8),np.ones((7,7),np.uint8)).astype(bool)
                                    for name,row in data.items():
                                        delta=(buffers[name][3]-shifts[name])[stable].astype(np.float64)*(3840/w)
                                        row['square']+=float(np.dot(delta,delta));row['n']+=delta.size
                                        norm=buffers[name][0];row['clipped']+=int(((norm<=0)|(norm>=1)).sum());row['pixels']+=norm.size
                                        row['severe']+=int((((norm<=0)&(reference>.05))|((norm>=1)&(reference<.95))).sum())
                                previous=rgb;shifts={name:b[3].copy() for name,b in buffers.items()}
                        finally:cap.release()
                        result={name:dict(low_motion_shift_rms_4k=(row['square']/max(1,row['n']))**.5,clipped_fraction=row['clipped']/max(1,row['pixels']),
                                          excess_clip_fraction_gt_005=row['severe']/max(1,row['pixels'])) for name,row in data.items()}
                        report['natural'].append(dict(size=[w,h],clip=clip,frames=count,result=result));save()
                        print(json.dumps(report['natural'][-1]),flush=True)
                finally:
                    for post in posts.values():post.close()
                    engine.close()
            report['max_natural_rms_increase']=max(r['result']['stable']['low_motion_shift_rms_4k']-r['result']['legacy']['low_motion_shift_rms_4k'] for r in report['natural'])
            assert report['max_natural_rms_increase']<=.1
            report['max_excess_clip_increase']=max(r['result']['stable']['excess_clip_fraction_gt_005']-r['result']['legacy']['excess_clip_fraction_gt_005'] for r in report['natural'])
            assert report['max_excess_clip_increase']<=.005
        report['passed']=True
    finally:save()


if __name__=='__main__':main()
