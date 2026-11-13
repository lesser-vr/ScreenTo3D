"""Matched-model native RGB/depth comparison against the former CPU correction.

Both consumers share each model token and source time. Background eligibility /
history invalidation remain identical. Native RGB mean error <=.1 byte and <=.5%
pixels with any channel error >8 per frame; depth MAE <=.0003, P99.9 <=.002,
max <=.01. Non-triggering scenes must be byte exact. Quality proxy only, not
physical 3D viewing or an FPS benchmark. All texture leases are read and retired.
"""
import argparse
import ctypes as ct
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np
import torch

from screento3d_app import ovda,da2_base
from screento3d_app.da2_base_device import Da2BaseDeviceEngine
from screento3d_app.desktop_jobs import ROOT,BUNDLE
from screento3d_app.gpu_frame import GpuFrame
from screento3d_app.live_model import model_adapter
from screento3d_app.live_policy import resolve_live
from screento3d_app.live_source_gpu_texture import LiveSourceGpuTexture
from screento3d_app.live_small_gpu_input import LiveSmallGpuInputTexture
from screento3d_app.small_gpu_input import SmallGpuCaptureEngine
from screento3d_app.resources import configure_resource_root
from screento3d_app.stereo import refine_flat_background
from uniform_background_tc import load_case,verify_asset


def reference_post(post):
    """Explicit diagnostic CPU oracle; ordinary product loading never uses it."""
    host_depth=np.empty((post.height,post.width),np.float32)
    original_post,original_project=post._post,post._project
    state=SimpleNamespace(refined=None)
    def legacy_post(frame,depth,aligned,reset):
        original_post(frame,depth,host_depth,reset)
        getattr(post.engine,'torch_stream',post.engine.stream).synchronize()
        rgb=frame.to_host()
        refined=refine_flat_background(rgb,host_depth,tolerance=post.policy.flat_background_tolerance,
                    minimum_coverage=post.policy.flat_background_min_coverage,radius=post.policy.depth_guide_radius)
        state.refined=None if refined is host_depth else refined
    post._post=legacy_post
    post._project=lambda frame,refined:original_project(frame,state.refined)
    post.flat_background=SimpleNamespace(
        apply=lambda *args:state.refined is not None,readback_bytes=0,syncs=0,close=lambda:None)
    return state


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--model',action='append',choices=('da2-small','da2-base','ovda-small-c16'))
    parser.add_argument('--strength',type=float,default=.5)
    parser.add_argument('--short',action='store_true')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    configure_resource_root(BUNDLE)
    report=dict(contract=__doc__,strength=args.strength,passed=False,rows=[])
    path=verify_asset(load_case());capture=cv2.VideoCapture(str(path))
    selected=[]
    for index in ((0,30,60,89) if args.short else (*range(0,90,4),89)):
        capture.set(cv2.CAP_PROP_POS_FRAMES,index);ok,bgr=capture.read();assert ok
        selected.append(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB))
    capture.release()
    try:
        for model in (args.model or ('da2-base','ovda-small-c16','da2-small')):
            policy=model_adapter(model).apply_live_policy(replace(resolve_live({'da2-base':'balanced','ovda-small-c16':'video-quality','da2-small':'performance'}[model],args.strength),
                    depth_backend=model,stereo_layout='half-tb'))
            for w,h in ((1920,1080),(3840,2160)):
                if model=='ovda-small-c16':engine=ovda.runtime_class(True)()
                elif model=='da2-base':
                    profiles=da2_base.profiles(ROOT/'out/da2-base-local');shape=(518,924)
                    engine=Da2BaseDeviceEngine(profiles[shape],BUNDLE/'runtime',shape)
                else:engine=SmallGpuCaptureEngine()
                posts={}
                try:
                    for name in ('gpu','cpu'):
                        post_type=LiveSmallGpuInputTexture if model=='da2-small' else LiveSourceGpuTexture
                        posts[name]=post_type(w,h,policy,engine,diagnostic=True)
                        posts[name].configure_live_quality('detail')
                        posts[name].dll.live_detail_snapshot.argtypes=[ct.c_void_p,ct.c_void_p]
                    reference=reference_post(posts['cpu'])
                    reads={name:np.empty((h,w),np.float32) for name in posts}
                    frames=[cv2.resize(rgb,(w,h)) for rgb in selected]
                    # Cut to a nonuniform, textured scene and back: exercise
                    # bypass exactness and reset after applied refinement.
                    rng=np.random.default_rng(39)
                    frames += [rng.integers(20,230,(h,w,3),np.uint8),frames[0],frames[-1]]
                    for index,rgb in enumerate(frames):
                        reset=index in (0,len(selected),len(selected)+1)
                        if reset:
                            if model=='ovda-small-c16':engine.reset('scene_cut')
                            for post in posts.values():post.reset()
                        with torch.cuda.stream(getattr(engine,'torch_stream',engine.stream)):
                            frame=GpuFrame(torch.from_numpy(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGRA)).to(engine.device),engine)
                        token=posts['gpu'].infer(frame)
                        complete=engine.complete_device;outputs={}
                        try:
                            with patch.object(engine,'complete_device',lambda value:value.validate()):
                                for name,post in posts.items():
                                    post.source_ns=1_000_000_000+index*16_666_667;post.slot=index%2
                                    slot=post.render(frame,token)
                                    rgba=np.empty((h,w,4),np.uint8)
                                    post.pool.check(post.pool.dll.live_pool_readback(post.pool.handle,slot,rgba.ctypes.data))
                                    post._check(post.dll.live_detail_snapshot(post.handle,reads[name].ctypes.data));outputs[name]=rgba
                        finally:complete(token)
                        error=np.abs(reads['gpu']-reads['cpu'])
                        rgb_error=np.abs(outputs['gpu'][:,:,:3].astype(np.int16)-outputs['cpu'][:,:,:3].astype(np.int16))
                        row=dict(model=model,size=[w,h],frame=index,reset=reset,applied=reference.refined is not None,
                                 depth_mae=float(error.mean()),depth_p999=float(np.quantile(error,.999)),depth_max=float(error.max()),
                                 rgb_mae=float(rgb_error.mean()),rgb_gt8_fraction=float((rgb_error.max(axis=2)>8).mean()))
                        report['rows'].append(row)
                        if not row['applied']:np.testing.assert_array_equal(outputs['gpu'],outputs['cpu'])
                        assert row['depth_mae']<=.0003 and row['depth_p999']<=.002 and row['depth_max']<=.01,row
                        assert row['rgb_mae']<=.1 and row['rgb_gt8_fraction']<=.005,row
                    print(json.dumps(dict(model=model,size=[w,h],frames=len(frames),passed=True)),flush=True)
                finally:
                    for post in posts.values():post.close()
                    engine.close()
        report['passed']=True
    finally:(args.output/'report.json').write_text(json.dumps(report,indent=2))


if __name__=='__main__':main()
