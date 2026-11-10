"""Paired public Base inference and independent GPU range-response checks."""
import argparse
import ctypes as ct
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path

import cv2
import numpy as np
import torch

from check_stereo_geometry_gpu import load, check_cuda
from depthsbs_app.da2_base import binding
from depthsbs_app.desktop_jobs import ROOT, BUNDLE
from depthsbs_app.live_policy import resolve_live
from depthsbs_app.live_scene_history import LiveSceneHistory
from public_test_media import PublicFrames, SOURCES, ATTRIBUTION

OLD = ROOT/'out/live-depth-coverage/live_depth.dll'
OLD_HASH = 'dfa9b515c5e078fb1befa9e37ad8ef7ec555a68828bf7f5dbd7e545f3e42171a'


def configure(dll):
    dll.live_snapshot.argtypes = [ct.c_void_p]*4
    if hasattr(dll, 'live_set_range_dt'):
        dll.live_set_range_dt.argtypes = [ct.c_void_p,ct.c_double]
    return dll


def allocate(stack, dll, width, height, stream):
    handle = ct.c_void_p()
    check_cuda(dll.live_create(ct.byref(handle),width,height,stream))
    stack.callback(lambda: check_cuda(dll.live_destroy(handle)))
    return handle


def post(dll, handle, rgb, raw, policy, reset, dt=-1):
    if hasattr(dll, 'live_set_range_dt'):
        check_cuda(dll.live_set_range_dt(handle,dt))
    aligned,normalized,smooth = [np.empty(raw.shape,np.float32) for _ in range(3)]
    bounds = np.empty(2,np.float64)
    check_cuda(dll.live_post_source(handle,rgb.ctypes.data,raw.ctypes.data,0,
        policy.depth_guide_radius,policy.temporal_alpha,policy.temporal_color_threshold,
        policy.temporal_depth_threshold,int(reset),aligned.ctypes.data,policy.temporal_depth_transition))
    check_cuda(dll.live_snapshot(handle,normalized.ctypes.data,smooth.ctypes.data,bounds.ctypes.data))
    assert np.isfinite(aligned).all() and np.isfinite(bounds).all() and bounds[0]<=bounds[1]
    return aligned,normalized,bounds


def synthetic(old, new, policy):
    stream = torch.cuda.Stream()
    rgb = np.full((32,128,3),100,np.uint8)
    base = np.tile(np.linspace(0,10,128,dtype=np.float32),(32,1))
    traces=[[],[]]
    with ExitStack() as stack:
        handles=[allocate(stack,d,128,32,stream.cuda_stream) for d in (old,new)]
        for i in range(180):
            raw=base.copy()
            # Only the far/near tails oscillate; central geometry is unchanged.
            raw[:,:6]+= .2 if i%2 else -.2
            raw[:,-6:]+= .2 if i%2 else -.2
            for k,dll in enumerate((old,new)):
                _,norm,bounds=post(dll,handles[k],rgb,raw,policy,i==0,1/60 if k else -1)
                traces[k].append(float(norm[:,32:96].mean()))
            if i==179:
                reset=post(new,handles[1],rgb,raw+20,policy,True,1/60)
                fresh=allocate(stack,new,128,32,stream.cuda_stream)
                control=post(new,fresh,rgb,raw+20,policy,True,1/60)
                assert all(np.array_equal(a,b) for a,b in zip(reset,control))
        jitter=[float(np.std(v[60:])) for v in traces]
        assert jitter[1]<jitter[0]*.5, jitter
        # Flat frames must remain finite and a reset must not carry stale bounds.
        _,norm,bounds=post(new,handles[1],rgb,np.ones_like(base)*8,policy,True,1/60)
        assert np.count_nonzero(norm)==0 and np.array_equal(bounds,[8,8])
        assert new.live_set_range_dt(handles[1],float('nan')) != 0
        assert new.live_set_range_dt(handles[1],.100001) != 0
        # A pure model affine drift must preserve stationary geometry, not lag it.
        affine=allocate(stack,new,128,32,stream.cuda_stream)
        first=post(new,affine,rgb,base,policy,True,1/60)[1]
        drift=post(new,affine,rgb,base*1.05+.2,policy,False,1/60)[1]
        affine_error=float(np.abs(first-drift).max())
        assert affine_error<2e-6,affine_error
        # No usable photometric anchors: fallback response uses elapsed time.
        responses=[]
        for hz in (30,60,120):
            handle=allocate(stack,new,128,32,stream.cuda_stream)
            start=post(new,handle,rgb,base,policy,True,1/hz)[2]
            for i in range(hz//2):
                moving=np.full_like(rgb,20 if i%2 else 220)
                end=post(new,handle,moving,base+.1,policy,False,1/hz)[2]
            responses.append(float(end[0]-start[0]))
        assert max(responses)-min(responses)<1e-6,responses
    return dict(stable_center_jitter=jitter,reset_exact=True,flat_finite=True,
                affine_normalized_max_error=affine_error,half_second_response_30_60_120=responses)


def benchmark(old,new,policy):
    stream=torch.cuda.Stream()
    rows=[]
    for width,height in ((1920,1080),(3840,2160)):
        with ExitStack() as stack:
            dlls=(old,new,new)
            handles=[allocate(stack,d,width,height,stream.cuda_stream) for d in dlls]
            with torch.cuda.stream(stream):
                rgb=torch.full((height,width,3),100,dtype=torch.uint8,device='cuda')
                raw=torch.linspace(0,10,width,device='cuda').repeat(height,1).contiguous()
            times=[[],[],[]]
            for iteration in range(27):
                for k in [(iteration+j)%3 for j in range(3)]:
                    dll,handle=dlls[k],handles[k]
                    if k: check_cuda(dll.live_set_range_dt(handle,1/60 if k==2 else -1))
                    start,end=torch.cuda.Event(enable_timing=True),torch.cuda.Event(enable_timing=True)
                    start.record(stream)
                    check_cuda(dll.live_post_source(handle,rgb.data_ptr(),raw.data_ptr(),2,
                        policy.depth_guide_radius,policy.temporal_alpha,policy.temporal_color_threshold,
                        policy.temporal_depth_threshold,int(iteration==0),None,policy.temporal_depth_transition))
                    end.record(stream)
                    end.synchronize()
                    if iteration>=6: times[k].append(start.elapsed_time(end))
            rows.append(dict(size=[width,height],gpu_post_median_ms=[float(np.median(t)) for t in times]))
    return rows


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--synthetic-only',action='store_true')
    parser.add_argument('--model',choices=('base','small'),default='base')
    parser.add_argument('--benchmark-only',action='store_true')
    args=parser.parse_args()
    cv2.setNumThreads(1)
    torch.set_num_threads(4)
    new_path=ROOT/'out/live-depth-range/live_depth.dll'
    digest=hashlib.sha256(new_path.read_bytes()).hexdigest()
    old,new=[configure(load(p,h)) for p,h in ((OLD,OLD_HASH),(new_path,digest))]
    policy=resolve_live('balanced' if args.model=='base' else 'performance',strength=.5)
    report=dict(passed=False,model=args.model,dll=digest,synthetic=synthetic(old,new,policy),clips=[],attribution=ATTRIBUTION)
    if args.benchmark_only:
        report['benchmark']=benchmark(old,new,policy)
        print(json.dumps(report['benchmark']),flush=True)
    elif not args.synthetic_only:
        with ExitStack() as stack:
            runtime=Path('C:/TensorRT/TensorRT-11.2.1.2/bin')
            stack.enter_context(os.add_dll_directory(str(runtime)))
            if args.model=='base':
                backend=binding(ROOT/'out/da2-base-local',runtime)
                backend.input_validator(dict(width=1920,height=1080))
                engine=stack.enter_context(backend.engine_factory(None))
                stream=engine.stream.cuda_stream
            else:
                from depthsbs_app.resources import configure_resource_root
                from depthsbs_app.trt_backend import DepthEngine
                from depthsbs_app.pipeline import preprocess
                configure_resource_root(BUNDLE)
                engine=stack.enter_context(DepthEngine())
                stream=int(engine.stream)
            xx,yy=np.meshgrid(np.arange(480,dtype=np.float32),np.arange(270,dtype=np.float32))
            for name in SOURCES:
                with ExitStack() as scene:
                    dlls=(old,new,new)
                    handles=[allocate(scene,d,1920,1080,stream) for d in dlls]
                    history=LiveSceneHistory(policy.scene_cut_threshold)
                    flow_engine=cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
                    previous=prior_gray=prior_bounds=None
                    rows=[]
                    for index,rgb in enumerate(PublicFrames(name,180)):
                        if index%2: continue
                        if args.model=='base':
                            raw=np.ascontiguousarray(engine.infer(rgb)[0])
                        else:
                            raw=cv2.resize(engine.infer(preprocess(rgb)).squeeze(),(1920,1080),interpolation=cv2.INTER_CUBIC)
                        event=history.inspect(rgb)
                        reset=previous is None or event.cut or index==90
                        results=[post(d,h,rgb,raw,policy,reset,1/30 if k==2 else -1)
                                 for k,(d,h) in enumerate(zip(dlls,handles))]
                        assert all(np.array_equal(a,b) for a,b in zip(results[0],results[1]))
                        if reset: assert all(np.array_equal(a,b) for a,b in zip(results[0],results[2]))
                        selected=[results[k] for k in (0,2)]
                        small=[cv2.resize(r[0],(480,270)) for r in selected]
                        gray=cv2.resize(cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY),(480,270))
                        row=dict(frame=index,reset=bool(reset),bounds=[r[2].tolist() for r in selected])
                        row['p95_abs_disparity_px']=[float(np.quantile(np.abs(d-policy.convergence),.95)*1920*policy.divergence) for d in small]
                        if not reset:
                            flow=flow_engine.calc(gray,prior_gray,None)
                            mx,my=xx+flow[:,:,0],yy+flow[:,:,1]
                            old_gray=cv2.remap(prior_gray,mx,my,cv2.INTER_LINEAR)
                            mask=(mx>1)&(mx<479)&(my>1)&(my<269)&(np.abs(gray.astype(float)-old_gray)<8)
                            edge=(cv2.dilate(small[0],np.ones((3,3),np.uint8))-cv2.erode(small[0],np.ones((3,3),np.uint8)))>.03
                            row['residual_px']=[]
                            row['range_only_px']=[]
                            row['clipped_fraction']=[]
                            for k,(aligned,norm,bounds) in enumerate(selected):
                                residual=np.abs(small[k]-cv2.remap(previous[k],mx,my,cv2.INTER_LINEAR))*1920*policy.divergence
                                row['residual_px'].append(dict(mean=float(residual[mask].mean()),edge=float(residual[mask&edge].mean())))
                                lo,hi=prior_bounds[k]
                                frozen=np.clip((raw-float(lo))/max(float(hi-lo),1e-6),0,1)
                                row['range_only_px'].append(float(np.abs(norm-frozen).mean()*1920*policy.divergence))
                                row['clipped_fraction'].append(float(((norm<=0)|(norm>=1)).mean()))
                        rows.append(row)
                        previous,prior_gray,prior_bounds=small,gray,[r[2] for r in selected]
                        history.commit(event)
                    measured=[r for r in rows if not r['reset']]
                    summary=dict(clip=name,frames=len(rows),legacy_exact=True,cut_exact=True,
                        residual_px=[{zone:float(np.mean([r['residual_px'][k][zone] for r in measured])) for zone in ('mean','edge')} for k in range(2)],
                        range_only_px=np.mean([r['range_only_px'] for r in measured],axis=0).tolist(),
                        clipped_fraction=np.mean([r['clipped_fraction'] for r in measured],axis=0).tolist())
                    summary['p95_abs_disparity_px']=np.mean([r['p95_abs_disparity_px'] for r in measured],axis=0).tolist()
                    report['clips'].append(dict(summary=summary,rows=rows))
                    print(json.dumps(summary),flush=True)
    report['passed']=True
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2))
    print(json.dumps(report['synthetic']),flush=True)


if __name__=='__main__':
    main()
