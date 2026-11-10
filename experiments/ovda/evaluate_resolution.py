# oVDA resolution/precision comparison, NC-SA-UHDV1.0; see LICENSE/README.md.
"""Matched causal c16 replay with current pixel/range processing and GPU input.

Four-factor comparison: 518 FP32 / 518 mixed FP16 / 392 FP32 / 392 mixed FP16.
Quality budgets, not ground-truth acceptance: mixed precision same-canvas raw
MAE <=.1% of FP32 P2/P98 span and native RGB MAE <=.25/255, <=1% pixels >8;
low resolution normalized dense MAE <=.02, edge MAE <=.04, native RGB MAE <=2,
<=5% pixels >8. Additional low-RGB-motion eye-shift RMS <=.1 pixel at 4K/.5
in every case. A failed quality budget excludes automatic default promotion.
Dense native/edge checks use selected frames; 32x32 projected-depth samples and
256x144 raw-depth samples cover every frame. No normal-speed visual acceptance.
"""
import argparse
import ctypes as ct
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import statistics
import time
import cv2
import numpy as np
import torch
from depthsbs_app.live_model import model_adapter
from depthsbs_app.live_policy import resolve_live
from depthsbs_app.live_source_gpu_texture import LiveSourceGpuTexture
from depthsbs_app.gpu_frame import GpuFrame
from depthsbs_app.stereo_layout import dimensions
from depthsbs_app.stereo_stability import sample_depth
from evaluate_precision import TimedContext,normalize
from trial_runtime import create_engine
from public_test_media import CORPUS

VARIANTS=('fp32-current','encoder-spatial','low-fp32','low-fp16')


def summary(values):
    return dict(mean=statistics.mean(values),max=max(values),median=statistics.median(values)) if values else None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    report=dict(contract=__doc__,cases=[],sources={},clock_hz=60,strength=.5,layout='half-tb',variants=list(VARIANTS))
    policy=model_adapter('ovda-small-c16').apply_live_policy(replace(resolve_live('video-quality',.5),
                         depth_backend='ovda-small-c16',stereo_layout='half-tb'))
    def save():(args.output/'report.json').write_text(json.dumps(report,indent=2))
    try:
        for w,h,count,clips in ((1280,720,180,('FloorballGame','OfficeWalk','ParkingGarage')),
                                 (3840,2160,90,('FloorballGame','OfficeWalk','ParkingGarage')),
                                 (1080,1920,64,('OfficeWalk',)),(3440,1440,64,('ParkingGarage',)),
                                 (1024,1024,64,('FloorballGame',))):
            engines={};posts={};rgba_buffers={}
            try:
                for v in VARIANTS:
                    engine=create_engine(v);engine.context=TimedContext(engine);engines[v]=engine
                    posts[v]=LiveSourceGpuTexture(w,h,policy,engine,diagnostic=True)
                    posts[v].dll.live_stereo_samples.argtypes=[ct.c_void_p,ct.c_void_p]
                    posts[v].dll.live_stereo_samples.restype=ct.c_int
                    ow,oh=dimensions(w,h,'half-tb');rgba_buffers[v]=np.empty((oh,ow,4),np.uint8)
                for clip in clips:
                    for v in VARIANTS:engines[v].reset('scene_cut');posts[v].reset()
                    path=CORPUS/(clip+'.mp4');digest=hashlib.sha256(path.read_bytes()).hexdigest()
                    assert digest==json.loads(path.with_suffix('.json').read_text())['sha256']
                    report['sources'][clip]=digest;cap=cv2.VideoCapture(str(path))
                    data={v:dict(engine_ms=[],infer_ms=[],raw_mae_percent=[],normalized_mae=[],dense_normalized_mae=[],
                                 edge_mae=[],temporal_error=[],native_mae=[],native_fraction_gt8=[],
                                 shift_square=0.,stable_points=0,cache_full_updates=0) for v in VARIANTS}
                    previous_rgb=None;previous_depth={};previous_projected={};cuts=0
                    selected=sorted(set((15,31,63,count-1)))
                    try:
                        for i in range(count):
                            ok,bgr=cap.read();assert ok,'Short public input'
                            rgb=np.ascontiguousarray(cv2.resize(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB),(w,h)))
                            if previous_rgb is not None:
                                cut=float(np.abs(cv2.resize(rgb,(32,32)).astype(np.float32)-cv2.resize(previous_rgb,(32,32))).mean())/255>policy.scene_cut_threshold
                                if cut:
                                    for v in VARIANTS:engines[v].reset('scene_cut');posts[v].reset()
                                    previous_depth={};previous_projected={};cuts+=1
                            small={};projected={};dense={};outputs={}
                            for v in VARIANTS:
                                engine,post=engines[v],posts[v]
                                with torch.cuda.stream(engine.stream):
                                    frame=GpuFrame(torch.from_numpy(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGRA)).to(engine.device),engine)
                                cached=engine.used
                                started=time.perf_counter();token=post.infer(frame)
                                data[v]['infer_ms'].append((time.perf_counter()-started)*1000)
                                engine.stream.synchronize() # Own restored depth before any diagnostic CPU read.
                                data[v]['engine_ms'].append(engine.context.elapsed())
                                with torch.cuda.stream(engine.stream):
                                    small[v]=torch.nn.functional.interpolate(token.tensor[:,None],size=(144,256),
                                                mode='bilinear',align_corners=True)[0,0].cpu().numpy().copy()
                                    if i in selected:dense[v]=token.tensor[0].cpu().numpy().copy()
                                post.source_ns=1_000_000_000+i*16_666_667;post.slot=i%2
                                slot=post.render(frame,token)
                                samples=np.empty((32,32),np.float32)
                                post._check(post.dll.live_stereo_samples(post.handle,samples.ctypes.data))
                                assert np.isfinite(samples).all() and np.isfinite(small[v]).all()
                                projected[v]=samples
                                if cached==15:data[v]['cache_full_updates']+=1
                                # Every published slot needs its diagnostic reader to return
                                # the keyed-mutex lease, including frames without dense metrics.
                                rgba=rgba_buffers[v]
                                post.pool.check(post.pool.dll.live_pool_readback(post.pool.handle,slot,rgba.ctypes.data))
                                if i in selected:
                                    assert (rgba[:,:,3]==255).all();outputs[v]=rgba[:,:,:3].copy()
                            ref,span=normalize(small['fp32-current'])
                            normals={v:normalize(small[v])[0] for v in VARIANTS}
                            if i>=16:
                                for v in VARIANTS[1:]:
                                    data[v]['raw_mae_percent'].append(float(np.abs(small[v]-small['fp32-current']).mean())/span*100)
                                    data[v]['normalized_mae'].append(float(np.abs(normals[v]-ref).mean()))
                                    if v in previous_depth:
                                        error=(normals[v]-previous_depth[v])-(ref-previous_depth['fp32-current'])
                                        data[v]['temporal_error'].append(float(np.abs(error).mean()))
                                if previous_rgb is not None and previous_projected:
                                    mask=np.max(np.abs(rgb.astype(np.int16)-previous_rgb.astype(np.int16)),axis=2)<=2
                                    mask=cv2.erode(mask.astype(np.uint8),np.ones((7,7),np.uint8))
                                    stable=sample_depth(mask).astype(bool)
                                    for v in VARIANTS:
                                        delta=(projected[v]-previous_projected[v])[stable].astype(np.float64)*(3840*policy.divergence*.5)
                                        data[v]['shift_square']+=float(np.dot(delta,delta));data[v]['stable_points']+=delta.size
                            if i in selected:
                                reference,span=normalize(dense['fp32-current'])
                                gradient=np.maximum(np.abs(np.diff(reference,axis=1,append=reference[:,-1:])),
                                                    np.abs(np.diff(reference,axis=0,append=reference[-1:,:])))
                                edge=cv2.dilate((gradient>.01).astype(np.uint8),np.ones((5,5),np.uint8)).astype(bool)
                                for v in VARIANTS[1:]:
                                    difference=np.abs(normalize(dense[v])[0]-reference)
                                    data[v]['dense_normalized_mae'].append(float(difference.mean()))
                                    data[v]['edge_mae'].append(float(difference[edge].mean()) if edge.any() else 0.)
                                    difference=np.abs(outputs[v].astype(np.int16)-outputs['fp32-current'].astype(np.int16))
                                    data[v]['native_mae'].append(float(difference.mean()))
                                    data[v]['native_fraction_gt8'].append(float(np.any(difference>8,axis=2).mean()))
                                if i==count-1:
                                    for v in VARIANTS:
                                        preview=cv2.resize(outputs[v],(960,round(outputs[v].shape[0]*960/outputs[v].shape[1])))
                                        cv2.imwrite(str(args.output/f'{w}x{h}-{clip}-{v}.png'),cv2.cvtColor(preview,cv2.COLOR_RGB2BGR))
                            previous_rgb=rgb;previous_depth=normals;previous_projected=projected
                    finally:cap.release()
                    results={}
                    for v,row in data.items():
                        results[v]={name:summary(value) for name,value in row.items() if isinstance(value,list)}
                        results[v].update(low_motion_eye_shift_rms_4k=(row['shift_square']/max(1,row['stable_points']))**.5,
                                          stable_points=row['stable_points'],full_cache_fraction=row['cache_full_updates']/max(1,count),
                                          cache_bytes=engines[v].telemetry()['cache_bytes'],profile=list(engines[v].profile),
                                          plan_sha256=engines[v].plan_hash)
                    row=dict(size=[w,h],clip=clip,frames=count,cuts=cuts,native_dense_frames=selected,results=results)
                    report['cases'].append(row);save()
                    print(json.dumps(dict(size=[w,h],clip=clip,results=results)),flush=True)
            finally:
                for post in posts.values():post.close()
                for engine in reversed(list(engines.values())):engine.context=engine.context.context;engine.close()
        decisions={}
        for v in VARIANTS[1:]:
            rows=[r['results'][v] for r in report['cases']]
            increased=max(r['results'][v]['low_motion_eye_shift_rms_4k']-r['results']['fp32-current']['low_motion_eye_shift_rms_4k'] for r in report['cases'])
            precision=v=='encoder-spatial'
            passed=(max(r['raw_mae_percent']['mean'] for r in rows)<=.1 if precision else
                    max(r['dense_normalized_mae']['mean'] for r in rows)<=.02 and max(r['edge_mae']['mean'] for r in rows)<=.04)
            passed=passed and increased<=.1 and max(r['native_mae']['mean'] for r in rows)<=(.25 if precision else 2.) and max(r['native_fraction_gt8']['max'] for r in rows)<=(.01 if precision else .05)
            decisions[v]=dict(quality_budget_pass=passed,max_additional_low_motion_rms_4k=increased)
        report['decisions']=decisions;report['completed']=True;save()
        print(json.dumps(decisions),flush=True)
    finally:save()


if __name__=='__main__':main()
