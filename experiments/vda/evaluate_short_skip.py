"""Sustained VDA capture-drop comparison against a full-rate model reference.

Contract fixed before execution: no-drop controls and first retained hard-cut
frames are exact in aligned depth/native pixels. For each clip/canvas, retaining
bounded single skips must have mean depth MAE <=.025 and no worse moving-edge
depth-change residual than reset-on-skips (5% + .00005 numerical margin); native
RGB MAE must be <= reset-on-skips + .05 byte/channel. These are relative fidelity
proxies against full-rate VDA, not depth ground truth or physical comfort.
"""
import argparse
from contextlib import ExitStack
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import torch

from depthsbs_app.desktop_jobs import BUNDLE
from depthsbs_app.gpu_frame import GpuFrame
from depthsbs_app.live_policy import resolve_live
from depthsbs_app.live_sbs import reset_reason
from depthsbs_app.live_source_gpu_texture import LiveSourceGpuTexture
from depthsbs_app.optional_models import installed_path
from depthsbs_app.resources import configure_resource_root
from depthsbs_app.vda_artifacts import artifact_profiles,select_artifact
from depthsbs_app.vda_device import VdaDeviceEngine
from public_test_media import CORPUS,SOURCES
from uniform_background_tc import load_case,verify_asset


def skipped(index,count):
    if index==count-1:return True
    if index<32 or index==count-2:return False
    block,offset=divmod(index-32,48)
    return offset%3==2 if block%2==0 else offset%11 in (2,5,9)


def frames(path,count,size):
    cap=cv2.VideoCapture(str(path))
    try:
        for _ in range(count):
            ok,bgr=cap.read()
            if not ok:
                cap.set(cv2.CAP_PROP_POS_FRAMES,0);ok,bgr=cap.read()
            if not ok:raise ValueError('Cannot decode quality fixture')
            yield np.ascontiguousarray(cv2.cvtColor(cv2.resize(bgr,size),cv2.COLOR_BGR2RGB))
    finally:cap.release()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    configure_resource_root(BUNDLE)
    report=dict(contract=__doc__,passed=False,cases=[],sources={},control_frames=0,hard_cut_frames=0)
    policy=replace(resolve_live('video-quality',.5),depth_backend='vda-small',stereo_layout='half-tb')
    profiles=artifact_profiles(installed_path('vda-small'))
    natural=[]
    for name in SOURCES:
        path=CORPUS/(name+'.mp4');digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if digest!=json.loads(path.with_suffix('.json').read_text())['sha256']:raise ValueError('Public fixture hash mismatch')
        natural.append((name,path));report['sources'][name]=digest
    flower=verify_asset(load_case());report['sources']['flower']=load_case()['sha256']
    try:
        for w,h,clips in ((1056,608,natural),(1920,1080,natural),(3840,2160,[('flower',flower)])):
            directory=select_artifact(profiles,dict(width=w,height=h))
            with ExitStack() as stack:
                owners=[];posts=[];prior=[None]*3;prior_ns=[None]*3
                for _ in range(3):
                    owner=stack.enter_context(VdaDeviceEngine(directory,BUNDLE/'runtime'))
                    post=stack.enter_context(LiveSourceGpuTexture(w,h,policy,owner,diagnostic=True))
                    owners.append(owner);posts.append(post)
                sequence=0
                def render(j,rgb):
                    owner,post=owners[j],posts[j]
                    timestamp=1_000_000_000+round(sequence*1e9/60)
                    with torch.cuda.stream(owner.stream):
                        frame=GpuFrame(torch.from_numpy(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGRA)).to(owner.device),owner)
                    scene=post.inspect_scene(frame)
                    reason=reset_reason(prior[j],sequence,(w,h),(w,h),scene.cut,
                        previous_source_ns=prior_ns[j],source_ns=timestamp,vda_single_skip=j==2)
                    if reason:
                        owner.reset({'start':'start','gap':'discontinuity','cut':'scene_cut'}[reason])
                        post.reset();scene=None
                    token=post.infer(frame);post.source_ns=timestamp;post.slot=sequence%2
                    slot,depth=post.render(frame,token,diagnostic=True,scene=scene)
                    pixels=np.empty((h,w,4),np.uint8)
                    post.pool.check(post.pool.dll.live_pool_readback(post.pool.handle,slot,pixels.ctypes.data))
                    prior[j]=sequence;prior_ns[j]=timestamp
                    return depth,pixels,reason
                for clip,path in clips:
                    metrics={j:dict(depth_sum=0.,moving_sum=0.,moving_pixels=0,rgb_sum=0.,pixels=0,
                                    updates=0,gap_resets=0,retained_skips=0) for j in (1,2)}
                    previous_error={};last_gray=None;drop_count=0
                    for index,rgb in enumerate(frames(path,192,(w,h))):
                        sequence+=1
                        expected,image,_=render(0,rgb)
                        if skipped(index,192):drop_count+=1;continue
                        gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
                        moving=None if last_gray is None else ((cv2.absdiff(gray,last_gray)>12)&(cv2.Canny(gray,50,120)>0))
                        for j in (1,2):
                            step=sequence-prior[j] if prior[j] is not None else None
                            depth,pixels,reason=render(j,rgb)
                            if index<32:
                                np.testing.assert_array_equal(depth,expected)
                                np.testing.assert_array_equal(pixels,image)
                                report['control_frames']+=1
                            residual=depth-expected
                            if index>=32:
                                row=metrics[j];row['depth_sum']+=float(np.abs(residual).sum(dtype=np.float64))
                                row['rgb_sum']+=float(cv2.absdiff(pixels,image)[:,:,:3].sum(dtype=np.float64))
                                row['pixels']+=w*h;row['updates']+=1;row['gap_resets']+=int(reason=='gap')
                                row['retained_skips']+=int(step==2 and reason is None)
                                if moving is not None and j in previous_error:
                                    values=np.abs(residual-previous_error[j])[moving]
                                    row['moving_sum']+=float(values.sum(dtype=np.float64));row['moving_pixels']+=values.size
                            previous_error[j]=residual;last_gray=gray
                    values={str(j):dict(depth_mae=v['depth_sum']/v['pixels'],
                        moving_change_mae=v['moving_sum']/max(1,v['moving_pixels']),
                        rgb_mae=v['rgb_sum']/(v['pixels']*3),updates=v['updates'],moving_pixels=v['moving_pixels'],
                        gap_resets=v['gap_resets'],retained_skips=v['retained_skips']) for j,v in metrics.items()}
                    row=dict(clip=clip,size=[w,h],canvas=directory.name,dropped=drop_count,result=values)
                    report['cases'].append(row)
                    old,new=values['1'],values['2']
                    assert new['moving_pixels']>0 and new['retained_skips']>20,row
                    assert new['gap_resets']==0 and old['gap_resets']>20,row
                    assert new['depth_mae']<=.025,row
                    assert new['moving_change_mae']<=old['moving_change_mae']*1.05+.00005,row
                    assert new['rgb_mae']<=old['rgb_mae']+.05,row
                    # Last source update was dropped. The white/black transition
                    # must still flush both cache and renderer at the next cut.
                    for color in (255,0):
                        for index in range(6):
                            sequence+=1;rgb=np.full((h,w,3),color,np.uint8)
                            expected,image,reference_reason=render(0,rgb)
                            for j in (1,2):
                                depth,pixels,reason=render(j,rgb)
                                if index==0:
                                    assert reference_reason=='cut' and reason in ('cut','gap'),(clip,j,reason)
                                    np.testing.assert_array_equal(depth,expected)
                                    np.testing.assert_array_equal(pixels,image)
                                    report['hard_cut_frames']+=1
                    (args.output/'report.json').write_text(json.dumps(report,indent=2))
                    print(json.dumps(row),flush=True)
        report['passed']=True
    finally:(args.output/'report.json').write_text(json.dumps(report,indent=2))


if __name__=='__main__':main()
