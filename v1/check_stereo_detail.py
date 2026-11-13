"""Controlled layered RGB truth and selective projection-depth checks."""
import argparse
from contextlib import ExitStack
import ctypes as ct
import hashlib
import json
import os
from pathlib import Path

import cv2
import numpy as np
import torch

from check_stereo_geometry_gpu import load, context, check_cuda
from check_stereo_stability_gpu import project
from check_stereo_window import setup as window_setup, settings
from check_disparity_budget import oracle
from screento3d_app.desktop_jobs import ROOT
from screento3d_app.live_gpu_candidate import DLL_PATH, DLL_SHA256


def setup(path, digest):
    dll = window_setup(load(path,digest))
    dll.live_set_detail.argtypes = [ct.c_void_p,ct.c_int]
    dll.live_set_disparity_budget.argtypes = [ct.c_void_p,ct.c_int]
    dll.live_detail_snapshot.argtypes = [ct.c_void_p,ct.c_void_p]
    dll.live_shift_snapshot.argtypes = [ct.c_void_p,ct.c_void_p]
    return dll


def render(dll,handle,rgb,depth,mode,convergence,scale):
    check_cuda(dll.live_set_detail(handle,mode))
    result = project(dll,handle,rgb,depth,convergence,scale)
    corrected = np.empty_like(depth)
    check_cuda(dll.live_detail_snapshot(handle,corrected.ctypes.data))
    return result,corrected


def synthetic(dll):
    stream = torch.cuda.Stream()
    width,height = 1920,16
    x = np.arange(width)
    rows=[]
    for thickness in (1,2,8,96):
        for strength in (.25,.5,1):
            scale=width*.026*strength
            start=width//2-thickness//2
            mask=((x>=start)&(x<start+thickness)).astype(float)
            bg=np.clip(90+(x-width//2)*.5,16,200)
            background=np.stack((bg,bg+10,bg+20),axis=1)
            foreground=np.array([220,40,30])
            rgb1=np.floor(background*(1-mask[:,None])+foreground*mask[:,None]+.5).astype(np.uint8)
            rgb=np.tile(rgb1[None],(height,1,1))
            depth=np.tile(np.where(mask,.9,.15).astype(np.float32)[None],(height,1))
            with ExitStack() as stack:
                handle=context(stack,dll,rgb,depth,stream)
                settings(dll,handle)
                check_cuda(dll.live_set_disparity_budget(handle,1))
                errors={0:[],2:[]}; residuals={0:[],2:[]}; last={}
                changed=0
                for convergence in np.linspace(.43,.47,21):
                    shifts=oracle((np.array([.15,.9]) - convergence)*scale,width)*.5
                    expected=[]
                    region=[]
                    for sign in (1,-1):
                        a=np.interp(x-sign*shifts[1],x,mask,left=0,right=0)
                        back=np.stack([np.interp(x-sign*shifts[0],x,background[:,k]) for k in range(3)],axis=1)
                        expected.append(back*(1-a[:,None])+foreground*a[:,None])
                        region.append((x>=start-16)&(x<start+thickness+16))
                    truth=np.concatenate(expected)
                    roi=np.concatenate(region)
                    outputs={}
                    for mode in (0,1,2,3):
                        output,z=render(dll,handle,rgb,depth,mode,float(convergence),scale)
                        assert np.array_equal(z,depth), 'Already sharp/thin depth changed'
                        outputs[mode]=output
                    assert np.array_equal(outputs[0],outputs[1])
                    assert np.array_equal(outputs[2],outputs[3])
                    opaque=np.concatenate([np.interp(x-sign*shifts[1],x,mask,left=0,right=0)>=.999999
                                           for sign in (1,-1)])
                    assert np.array_equal(outputs[0][:,opaque],outputs[2][:,opaque])
                    changed+=int(np.any(outputs[0]!=outputs[2]))
                    for mode in (0,2):
                        error=outputs[mode][height//2].astype(float)-truth
                        errors[mode].append(float(np.abs(error[roi]).mean()))
                        if mode in last:
                            residuals[mode].append(float(np.abs((error-last[mode])[roi]).mean()))
                        last[mode]=error
                values=[float(np.mean(errors[m])) for m in (0,2)]
                temporal=[float(np.mean(residuals[m])) for m in (0,2)]
                assert values[1] <= values[0]+.01,(thickness,strength,values)
                assert temporal[1] <= temporal[0]+.02,(thickness,strength,temporal)
                rows.append(dict(thickness=thickness,strength=strength,rgb_mae=values,
                                 temporal_error=temporal,changed_frames=changed))
    # Isolated intermediate-depth fringe with matching RGB: correction must move
    # toward the known surface, preserve unrelated pixels, and never feed history.
    rgb=np.zeros((16,128,3),np.uint8)
    rgb[:,:64]=[30,50,60];rgb[:,64:]=[200,160,100]
    truth=np.full((16,128),.2,np.float32);truth[:,64:]=.8
    fringe=truth.copy();fringe[:,64]=.5
    with ExitStack() as stack:
        handle=context(stack,dll,rgb,fringe,stream);settings(dll,handle)
        outputs=[]
        for mode in (0,1,2,3):
            output,z=render(dll,handle,rgb,fringe,mode,.45,12.48)
            outputs.append(z)
            if mode&1:
                assert np.all(z[:,64]>.5)
                assert float(np.abs(z-truth).mean())<float(np.abs(fringe-truth).mean())
                assert np.max(np.abs(z-fringe))<=.025001
                assert np.array_equal(z[:,:64],fringe[:,:64])
                assert np.array_equal(z[:,65:],fringe[:,65:])
            else:
                assert np.array_equal(z,fringe)
        assert np.array_equal(outputs[1],outputs[3])
        # Color edge absent: the same uncertain depth must be untouched.
        rgb[:]=100
        check_cuda(dll.live_post_source(handle,rgb.ctypes.data,fringe.ctypes.data,0,1,.35,.04,.08,1,None,.008))
        _,z=render(dll,handle,rgb,fringe,3,.45,12.48)
        assert np.array_equal(z,fringe)
        assert dll.live_set_detail(handle,4)!=0 and dll.live_set_detail(None,1)!=0
    return dict(layered=rows,thin_sharp_exact=True,contour_bound=True,
                color_gate_exact=True,independent_flags=True)


def shapes(dll):
    from screento3d_app.live_texture_pool import LiveTexturePool
    old=window_setup(load(ROOT/'out/live-depth-budget/live_depth.dll',
                         '6d37f9b85e5a72e53b2ce693e51a51f9911a609bbdc9e4885cccdff35e5a228e'))
    old.live_set_disparity_budget.argtypes=[ct.c_void_p,ct.c_int]
    stream=torch.cuda.Stream()
    rows=[]
    for width,height in ((16,16),(64,32),(1920,1080),(3440,1440),
                         (1080,1920),(3840,2160),(4096,2160)):
        rgb=np.random.default_rng(36).integers(0,256,(height,width,3),np.uint8)
        depth=np.full((height,width),.2,np.float32)
        depth[:,width//2:]=.8;depth[:,width//2]=.5
        rgb[:,width//2]=rgb[:,width//2+1]
        with ExitStack() as stack:
            handle=context(stack,dll,rgb,depth,stream)
            prior=context(stack,old,rgb,depth,stream)
            pool=stack.enter_context(LiveTexturePool(width,height,diagnostic=True))
            for lib,h in ((dll,handle),(old,prior)):
                settings(lib,h)
                check_cuda(lib.live_set_disparity_budget(h,1))
                check_cuda(lib.live_set_window(h,1/60,1))
            base,_=render(dll,handle,rgb,depth,0,.45,width*.0065)
            old_shift=np.empty_like(depth)
            check_cuda(dll.live_shift_snapshot(handle,old_shift.ctypes.data))
            assert np.array_equal(base,project(old,prior,rgb,depth,.45,width*.0065))
            current,_=render(dll,handle,rgb,depth,3,.45,width*.0065)
            new_shift=np.empty_like(depth)
            check_cuda(dll.live_shift_snapshot(handle,new_shift.ctypes.data))
            assert np.array_equal(np.floor(old_shift),np.floor(new_shift))
            assert np.array_equal(np.ceil(old_shift),np.ceil(new_shift))
            pool.check(pool.dll.live_pool_publish(pool.handle,handle,.45,width*.0065,1,None,0,0))
            native=np.empty((height,width*2,4),np.uint8)
            pool.check(pool.dll.live_pool_readback(pool.handle,0,native.ctypes.data))
            assert np.array_equal(current,native[:,:,:3]) and np.all(native[:,:,3]==255)
            # Textured single planes and zero-shift source pixels are unchanged.
            for plane in (.2,.45,.8):
                depth[:]=plane
                check_cuda(dll.live_set_window(handle,1/60,1))
                base,_=render(dll,handle,rgb,depth,0,.45,width*.0065)
                check_cuda(dll.live_set_window(handle,1/60,1))
                current,_=render(dll,handle,rgb,depth,3,.45,width*.0065)
                assert np.array_equal(base,current)
            rows.append(dict(size=[width,height],disabled_exact=True,native_exact=True,flat_exact=True))
    return rows


def public(dll,model,output):
    from check_depth_range import allocate,post
    from screento3d_app.live_policy import resolve_live
    from screento3d_app.live_scene_history import LiveSceneHistory
    from screento3d_app.motion_history import MotionHistory
    from public_test_media import PublicFrames,SOURCES
    policy=resolve_live('balanced' if model=='base' else 'performance',strength=.25)
    results=[]
    with ExitStack() as stack:
        runtime=Path('C:/TensorRT/TensorRT-11.2.1.2/bin')
        stack.enter_context(os.add_dll_directory(str(runtime)))
        if model=='base':
            from screento3d_app.da2_base import binding
            backend=binding(ROOT/'out/da2-base-local',runtime)
            backend.input_validator(dict(width=1920,height=1080))
            engine=stack.enter_context(backend.engine_factory(None));stream=engine.stream
        else:
            from screento3d_app.desktop_jobs import BUNDLE
            from screento3d_app.resources import configure_resource_root
            from screento3d_app.small_gpu_input import SmallGpuCaptureEngine
            from screento3d_app.pipeline import preprocess
            configure_resource_root(BUNDLE)
            engine=stack.enter_context(SmallGpuCaptureEngine());stream=engine.torch_stream
        for name in SOURCES:
            with ExitStack() as scene:
                handle=allocate(scene,dll,1920,1080,stream.cuda_stream)
                settings(dll,handle)
                check_cuda(dll.live_set_disparity_budget(handle,1))
                motion=scene.enter_context(MotionHistory(1920,1080,stream.cuda_stream,DLL_SHA256,diagnostic=True))
                history=LiveSceneHistory(policy.scene_cut_threshold)
                rows=[];best=-1;best_image=None
                for index,rgb in enumerate(PublicFrames(name,90)):
                    raw=(np.ascontiguousarray(engine.infer(rgb)[0]) if model=='base' else
                         cv2.resize(engine.infer(preprocess(rgb)).squeeze(),(1920,1080),interpolation=cv2.INTER_CUBIC))
                    event=history.inspect(rgb);reset=index in (0,45) or event.cut
                    post(dll,handle,rgb,raw,policy,reset,1/60)
                    motion.apply(handle,1_000_000_000+index*16_666_667,reset=reset)
                    depth=motion.snapshot(handle)[0]
                    outputs=[];depths=[]
                    for mode in (0,1,2,3):
                        # Same depth, isolate quality from the mask's temporal release.
                        check_cuda(dll.live_set_window(handle,1/60,1))
                        image,z=render(dll,handle,rgb,depth,mode,policy.convergence,1920*policy.divergence)
                        outputs.append(image);depths.append(z)
                    assert np.array_equal(depths[0],depth) and np.array_equal(depths[2],depth)
                    assert np.array_equal(depths[1],depths[3])
                    assert np.array_equal(motion.snapshot(handle)[0],depth), 'Projection mutated history input'
                    correction=np.abs(depths[1]-depth)
                    assert correction.max()<=.025001
                    diffs=[np.max(np.abs(a.astype(np.int16)-outputs[0].astype(np.int16)),axis=2) for a in outputs[1:]]
                    row=dict(index=index,reset=bool(reset),contour_fraction=float((correction>1e-7).mean()),
                             max_depth_correction=float(correction.max()),
                             changed_fraction=[float((d>1).mean()) for d in diffs],
                             mean_rgb_max_delta=[float(d.mean()) for d in diffs],
                             max_rgb_delta=[int(d.max()) for d in diffs])
                    rows.append(row)
                    score=row['changed_fraction'][2]
                    if score>best:
                        best=score
                        # Highest-changing 320x180 left-eye tile, shown at 1:1.
                        tiles=diffs[2][:,:1920].reshape(6,180,6,320).sum(axis=(1,3))
                        iy,ix=np.unravel_index(tiles.argmax(),tiles.shape)
                        sy,sx=slice(iy*180,(iy+1)*180),slice(ix*320,(ix+1)*320)
                        crops=[]
                        for title,image in zip(('Source','Budget','Contour','Fill','Combined'),[rgb,*outputs]):
                            crop=cv2.copyMakeBorder(cv2.cvtColor(image[sy,sx],cv2.COLOR_RGB2BGR),26,0,0,0,cv2.BORDER_CONSTANT)
                            cv2.putText(crop,title,(8,18),cv2.FONT_HERSHEY_SIMPLEX,.5,(255,255,255),1)
                            crops.append(crop)
                        best_image=np.concatenate(crops,axis=1)
                    history.commit(event)
                summary=dict(model=model,clip=name,frames=len(rows),strength=.25,
                    mean_contour_fraction=float(np.mean([r['contour_fraction'] for r in rows])),
                    max_depth_correction=max(r['max_depth_correction'] for r in rows),
                    mean_changed_fraction=np.mean([r['changed_fraction'] for r in rows],axis=0).tolist(),
                    mean_rgb_max_delta=np.mean([r['mean_rgb_max_delta'] for r in rows],axis=0).tolist())
                assert cv2.imwrite(str(output.parent/f'{model}-{name}-changes.png'),best_image)
                print(json.dumps(summary),flush=True)
                results.append(dict(summary=summary,rows=rows))
    return results


def benchmark(dll):
    from screento3d_app.live_texture_pool import LiveTexturePool
    from public_test_media import PublicFrames
    stream=torch.cuda.Stream();rows=[]
    for width,height in ((1920,1080),(3840,2160)):
        rgb=cv2.resize(PublicFrames('FloorballGame',1)[0],(width,height))
        depth=np.full((height,width),.2,np.float32)
        # Many foreground stripes stress the hole path instead of a flat plane.
        for x in range(32,width-32,64):depth[:,x:x+24]=.9
        with ExitStack() as stack:
            handle=context(stack,dll,rgb,depth,stream);settings(dll,handle)
            check_cuda(dll.live_set_disparity_budget(handle,1))
            check_cuda(dll.live_set_window(handle,1/60,1))
            render(dll,handle,rgb,depth,0,.45,width*.0065)
            pool=stack.enter_context(LiveTexturePool(width,height,diagnostic=True))
            readback=np.empty((height,width*2,4),np.uint8);times={m:[] for m in range(4)}
            for iteration in range(40):
                for mode in (range(4) if iteration%2 else reversed(range(4))):
                    check_cuda(dll.live_set_detail(handle,mode))
                    start,end=torch.cuda.Event(enable_timing=True),torch.cuda.Event(enable_timing=True)
                    start.record(stream)
                    pool.check(pool.dll.live_pool_publish(pool.handle,handle,.45,width*.0065,1,None,0,0))
                    end.record(stream);end.synchronize()
                    if iteration>=10:times[mode].append(start.elapsed_time(end))
                    pool.check(pool.dll.live_pool_readback(pool.handle,0,readback.ctypes.data))
            rows.append(dict(size=[width,height],samples=30,
                             median_ms=[float(np.median(times[m])) for m in range(4)],
                             p95_ms=[float(np.percentile(times[m],95)) for m in range(4)]))
    return rows


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--dll',type=Path,default=DLL_PATH)
    parser.add_argument('--sha256',default=DLL_SHA256)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--model',choices=('base','small'))
    parser.add_argument('--benchmark',action='store_true')
    args=parser.parse_args()
    assert hashlib.sha256(args.dll.read_bytes()).hexdigest()==args.sha256
    args.output.parent.mkdir(parents=True,exist_ok=True)
    cv2.setNumThreads(1);torch.set_num_threads(4)
    dll=setup(args.dll,args.sha256)
    result=dict(passed=False,dll=args.sha256)
    if args.model:
        from public_test_media import ATTRIBUTION
        result.update(public=public(dll,args.model,args.output),attribution=ATTRIBUTION)
    elif args.benchmark:result['benchmark']=benchmark(dll)
    else:result.update(synthetic=synthetic(dll),shapes=shapes(dll))
    result['passed']=True
    args.output.write_text(json.dumps(result,indent=2))
    print('Passed',flush=True)


if __name__=='__main__':main()
