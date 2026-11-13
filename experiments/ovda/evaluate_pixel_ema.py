# oVDA EMA comparison, NC-SA-UHDV1.0; see LICENSE/README.md.
"""Native pixel-EMA response/stability comparison with fixed range/model history.

Contract: .18 bridge equals legacy; bounds/pre-EMA normalization equal for every
weight. Prefer the fastest step response whose additional low-RGB-motion shift
RMS stays <=0.1 eye pixel at width 3840/strength .5 in every natural case.
These are response/stability proxies, not depth ground truth or physical comfort.
"""
import argparse
import ctypes as ct
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import statistics
import threading
from unittest.mock import patch
import cv2
import numpy as np
import torch
from screento3d_app import ovda
from screento3d_app.desktop_jobs import ROOT
from screento3d_app.live_policy import resolve_live
from screento3d_app.live_source_gpu_texture import LiveSourceGpuTexture
from screento3d_app.gpu_frame import GpuFrame
from screento3d_app.ovda_geometry import select_profile
from screento3d_app.stereo_layout import dimensions
from public_test_media import CORPUS

WEIGHTS=(.18,.5,.75,1.)


class FixtureOwner:
    def __init__(self,w,h):
        self.torch=torch;self.device=torch.cuda.current_device();self.stream=torch.cuda.Stream()
        self.owner=threading.get_ident();self.closed=False;self.shape=(h,w,3)
        self.pending_device=None;self.device_generation=0
    def check(self):
        if self.closed or self.owner!=threading.get_ident() or self.device!=torch.cuda.current_device():
            raise RuntimeError('Foreign or closed fixture owner')
    def complete_device(self,token):
        token.validate();self.stream.synchronize();self.pending_device=None
    def token(self,raw):
        from _screento3d_ovda.device_depth import OvdaDeviceDepth
        with torch.cuda.stream(self.stream):value=torch.from_numpy(raw[None]).to(self.device)
        self.device_generation+=1
        token=OvdaDeviceDepth(self,self.device_generation,value,int(self.stream.cuda_stream),(value,))
        self.pending_device=token
        return token
    def close(self):
        self.stream.synchronize();self.pending_device=None;self.closed=True


def readers(post,w,h):
    post.dll.live_snapshot.argtypes=[ct.c_void_p]*4
    post.dll.live_shift_snapshot.argtypes=[ct.c_void_p]*2
    return (np.empty((h,w),np.float32),np.empty((h,w),np.float32),np.empty(2,np.float64),np.empty((h,w),np.float32))


def render_all(engine,posts,frame,token,index,buffers,w,h):
    outputs={}
    # All independent postprocessors consume the same pending depth on its owner
    # stream. Defer exactly one real completion until every consumer finishes.
    complete=engine.complete_device
    try:
        with patch.object(engine,'complete_device',lambda value:value.validate()):
            for name,post in posts.items():
                post.slot=index%2
                slot=post.render(frame,token)
                ow,oh=dimensions(w,h,'half-tb');rgba=np.empty((oh,ow,4),np.uint8)
                post.pool.check(post.pool.dll.live_pool_readback(post.pool.handle,slot,rgba.ctypes.data))
                normalized,smooth,bounds,shift=buffers[name]
                post._check(post.dll.live_snapshot(post.handle,normalized.ctypes.data,smooth.ctypes.data,bounds.ctypes.data))
                post._check(post.dll.live_shift_snapshot(post.handle,shift.ctypes.data))
                assert np.isfinite(normalized).all() and np.isfinite(smooth).all() and np.isfinite(shift).all()
                outputs[name]=rgba
    finally:complete(token)
    base=buffers['legacy']
    for name,values in buffers.items():
        np.testing.assert_array_equal(values[0],base[0])
        np.testing.assert_array_equal(values[2],base[2])
    np.testing.assert_array_equal(buffers['0.18'][1],base[1])
    np.testing.assert_array_equal(outputs['0.18'],outputs['legacy'])
    return outputs


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    cls=ovda.runtime_class(True)
    from _screento3d_ovda.postprocess import OvdaGpuTexture
    report=dict(contract=__doc__,sources={},synthetic={},natural=[])
    policy=replace(resolve_live('video-quality',.5),stereo_layout='half-tb')
    def make_posts(engine,w,h):
        posts={}
        try:
            posts['legacy']=LiveSourceGpuTexture(w,h,policy,engine,diagnostic=True)
            for weight in WEIGHTS:posts[str(weight)]=OvdaGpuTexture(w,h,policy,engine,diagnostic=True,pixel_alpha=weight)
            return posts,{name:readers(post,w,h) for name,post in posts.items()}
        except BaseException:
            for post in posts.values():post.close()
            raise
    try:
        w,h=512,288;engine=FixtureOwner(w,h);posts={}
        try:
            posts,buffers=make_posts(engine,w,h)
            rgb=np.full((h,w,3),120,np.uint8)
            ramp=np.tile(np.linspace(.1,.9,w,dtype=np.float32),(h,1))
            roi=(slice(90,198),slice(200,312));samples={name:[] for name in posts}
            for i in range(72):
                raw=ramp.copy();raw[roi]=.45 if i<36 else .49
                render_all(engine,posts,rgb,engine.token(raw),i,buffers,w,h)
                for name in posts:samples[name].append(float(buffers[name][1][roi].mean()))
            for name,values in samples.items():
                target=float(buffers[name][0][roi].mean());initial=values[35]
                settled=next((j+1 for j,v in enumerate(values[36:]) if abs(target-v)<=abs(target-initial)*.1),None)
                report['synthetic'][name]=dict(step_t90_updates=settled,initial=initial,target=target,response=values[36:])
            report['synthetic_parity_frames']=72
        finally:
            for post in posts.values():post.close()
            engine.close()
        profiles=ovda.profiles(ROOT/'out/ovda-local')
        for w,h,count in ((1280,720,64),(720,1280,48),(3840,2160,20)):
            shape=select_profile(w,h,profiles);engine=cls(directory=profiles[shape],profile=shape);posts={}
            try:
                posts,buffers=make_posts(engine,w,h)
                for clip in ('FloorballGame','OfficeWalk','ParkingGarage'):
                    engine.reset('scene_cut')
                    for post in posts.values():post.reset()
                    path=CORPUS/(clip+'.mp4');digest=hashlib.sha256(path.read_bytes()).hexdigest()
                    if digest!=json.loads(path.with_suffix('.json').read_text())['sha256']:raise ValueError('Public source identity changed')
                    report['sources'][clip]=digest
                    cap=cv2.VideoCapture(str(path));previous_rgb=None;previous_shift={}
                    data={name:dict(change_sq=0.,stable_pixels=0,debt_sq=0.,pixels=0,sbs_mae=[]) for name in posts}
                    try:
                        for i in range(count):
                            ok,bgr=cap.read()
                            if not ok:raise ValueError('Short public input')
                            rgb=np.ascontiguousarray(cv2.resize(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB),(w,h)))
                            with torch.cuda.stream(engine.stream):
                                frame=GpuFrame(torch.from_numpy(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGRA)).to(engine.device),engine)
                            token=engine.infer_device(frame)
                            outputs=render_all(engine,posts,frame,token,i,buffers,w,h)
                            if previous_rgb is not None and i>=8:
                                stable=np.max(np.abs(rgb.astype(np.int16)-previous_rgb.astype(np.int16)),axis=2)<=2
                                stable=cv2.erode(stable.astype(np.uint8),np.ones((7,7),np.uint8)).astype(bool)
                                for name,row in data.items():
                                    normalized,smooth,bounds,shift=buffers[name]
                                    delta=(shift-previous_shift[name])[stable].astype(np.float64)*(3840/w)
                                    row['change_sq']+=float(np.dot(delta,delta));row['stable_pixels']+=delta.size
                                    debt=(smooth-normalized).astype(np.float64)*(3840*.015*.5)
                                    row['debt_sq']+=float(np.square(debt).sum());row['pixels']+=debt.size
                                    row['sbs_mae'].append(float(np.abs(outputs[name].astype(np.int16)-outputs['legacy'].astype(np.int16)).mean()))
                            previous_rgb=rgb
                            previous_shift={name:value[3].copy() for name,value in buffers.items()}
                    finally:cap.release()
                    result={name:dict(low_rgb_motion_shift_rms_4k=(v['change_sq']/max(1,v['stable_pixels']))**.5,
                                      ema_tracking_rms_4k=(v['debt_sq']/max(1,v['pixels']))**.5,
                                      stable_pixels=v['stable_pixels'],sbs_mae=statistics.mean(v['sbs_mae'])) for name,v in data.items()}
                    row=dict(size=[w,h],clip=clip,frames=count,result=result)
                    report['natural'].append(row)
                    (args.output/'report.json').write_text(json.dumps(report,indent=2))
                    print(json.dumps(row),flush=True)
            finally:
                for post in posts.values():post.close()
                engine.close()
        eligible=[]
        for weight in WEIGHTS[1:]:
            name=str(weight)
            increases=[r['result'][name]['low_rgb_motion_shift_rms_4k']-r['result']['legacy']['low_rgb_motion_shift_rms_4k'] for r in report['natural']]
            eligible.append(dict(weight=weight,max_shift_rms_increase=max(increases),within_budget=max(increases)<=.1,
                                 t90=report['synthetic'][name]['step_t90_updates']))
        report['candidates']=eligible
        passing=[c for c in eligible if c['within_budget'] and c['t90'] is not None]
        report['selected']=min(passing,key=lambda c:(c['t90'],c['weight']))['weight'] if passing else None
        report['passed']=True
    finally:(args.output/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(dict(candidates=report['candidates'],selected=report['selected'])),flush=True)


if __name__=='__main__':main()
