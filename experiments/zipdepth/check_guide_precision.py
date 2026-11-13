"""Matched-input guide precision experiment; quality tolerances are NOT exact parity.

Per frame: depth MAE <=1e-6/max <=1e-4; SBS channel MAE <=.05/255,
fraction of pixels with >1 channel-level error <=.001 in EACH eye;
edge-band channel MAE <=.20/255; temporal difference-of-errors MAE <=.10/255.
Test both guide output and downstream motion history; masks/scene/reset are shared.
No image resizing, model change or altered guide radius is part of the candidate.
"""
import argparse,hashlib,json,sys,time
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'v1'))

def main():
    import cv2,numpy as np,torch
    from check_stereo_geometry_gpu import context,check_cuda
    from check_stereo_detail import setup
    from check_stereo_window import settings
    from screento3d_app.live_texture_pool import LiveTexturePool
    from screento3d_app import motion_history
    from screento3d_app.live_scene_history import LiveSceneHistory
    from screento3d_app.live_policy import resolve_live
    from public_test_media import PublicFrames
    p=argparse.ArgumentParser()
    p.add_argument('--candidate',choices=['guide-fp32','guide-compensated'],required=True)
    p.add_argument('--public',action='store_true')
    p.add_argument('--native4k',action='store_true',help='Matched genuine UVG 4K120 detail, no upscaling')
    p.add_argument('--tag',choices=['residual','final'],default=None)
    p.add_argument('--model',choices=['zipdepth','small'],default='zipdepth')
    args=p.parse_args();out=ROOT/'out'/args.candidate
    if args.public and args.native4k:p.error('Choose one public corpus')
    target=out/('quality-native4k.json' if args.native4k else 'quality-public.json' if args.public else 'quality-synthetic.json')
    if args.tag:target=target.with_stem(target.stem+'-'+args.tag)
    if args.model!='zipdepth':target=target.with_stem(target.stem+'-'+args.model)
    if target.exists():raise FileExistsError(target)
    sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
    current=ROOT/'out/gpu-load-opt/live_depth.dll'
    assert sha(current)=='a1abad814853a74890214f8cc95e9be853f107a7479ab3aad1afb0fda441afee'
    paths=[current,out/'live_depth.dll'];hashes=[sha(f) for f in paths]
    libs=[setup(f,h) for f,h in zip(paths,hashes)]
    stream=torch.cuda.Stream();cv2.setNumThreads(1);torch.set_num_threads(1)
    report=dict(completed=False,passed=False,candidate=args.candidate,model=args.model,hashes=hashes,
        contract=__doc__,rows=[],failures=[],timing_scope='Diagnostic post including depth readback, not live FPS')
    rng=np.random.default_rng(1106)
    policy=replace(resolve_live('performance',.25),depth_guide_radius=4)
    report['policy']=dict(radius=policy.depth_guide_radius,convergence=policy.convergence,
                          divergence=policy.divergence,scene_cut_threshold=policy.scene_cut_threshold)

    def sequence(label,w,h,frames,with_motion,dt=1/60):
        history=LiveSceneHistory(policy.scene_cut_threshold);previous_error=None
        with ExitStack() as stack:
            dummy=np.zeros((h,w,3),np.uint8);raw=np.zeros((h,w),np.float32)
            handles=[context(stack,lib,dummy,raw,stream) for lib in libs]
            pools=[stack.enter_context(LiveTexturePool(w,h,diagnostic=True)) for _ in libs]
            stack.enter_context(patch.object(motion_history,'LAYOUTS',motion_history.LAYOUTS|frozenset(hashes)))
            motions=[stack.enter_context(motion_history.MotionHistory(w,h,stream.cuda_stream,digest,diagnostic=True))
                     if with_motion else None for digest in hashes]
            for lib,handle in zip(libs,handles):
                settings(lib,handle);check_cuda(lib.live_set_disparity_budget(handle,1));check_cuda(lib.live_set_detail(handle,3))
            for index,(rgb,depth,forced_reset) in enumerate(frames):
                scene=history.inspect(rgb);reset=forced_reset or scene.cut or index==0
                with torch.cuda.stream(stream):
                    drgb=torch.from_numpy(np.ascontiguousarray(rgb)).cuda()
                    draw=depth if isinstance(depth,torch.Tensor) else torch.from_numpy(np.ascontiguousarray(depth)).cuda()
                aligned=[];post_motion=[];images=[];times=[]
                for lib,handle,pool,motion in zip(libs,handles,pools,motions):
                    z=np.empty((h,w),np.float32)
                    check_cuda(lib.live_set_range_dt(handle,dt));check_cuda(lib.live_set_window(handle,dt,int(reset)))
                    begin=time.perf_counter_ns()
                    check_cuda(lib.live_post_source(handle,drgb.data_ptr(),draw.data_ptr(),2,policy.depth_guide_radius,.55,.04,.08,int(reset),z.ctypes.data,.008))
                    stream.synchronize();times.append((time.perf_counter_ns()-begin)/1e6)
                    aligned.append(z)
                    if motion:
                        motion.apply(handle,1_000_000_000+round(index*dt*1e9),reset=reset)
                        z=motion.snapshot(handle)[0]
                    post_motion.append(z)
                    image=np.empty((h,w*2,4),np.uint8)
                    pool.check(pool.dll.live_pool_publish(pool.handle,handle,policy.convergence,w*policy.divergence,1,None,0,0))
                    pool.check(pool.dll.live_pool_readback(pool.handle,0,image.ctypes.data))
                    assert np.all(image[:,:,3]==255)
                    images.append(image[:,:,:3])
                history.commit(scene)
                row=dict(sequence=label,size=[w,h],index=index,reset=bool(reset),motion=with_motion,source_dt=dt,post_diagnostic_ms=times)
                for name,values in (('guide',aligned),('motion',post_motion)):
                    delta=np.abs(values[0]-values[1])
                    row[name+'_mae']=float(delta.mean());row[name+'_max']=float(delta.max())
                error=images[1].astype(np.int16)-images[0].astype(np.int16);absolute=np.abs(error)
                row['rgb_mae']=float(absolute.mean());row['rgb_max']=int(absolute.max())
                row['eye_changed_over1']=[float((absolute[:,x:x+w].max(axis=2)>1).mean()) for x in (0,w)]
                gradient=cv2.dilate(aligned[0],np.ones((3,3),np.uint8))-cv2.erode(aligned[0],np.ones((3,3),np.uint8))
                edge=cv2.dilate((gradient>.02).astype(np.uint8),np.ones((7,7),np.uint8)).astype(bool)
                edge=np.concatenate((edge,edge),axis=1)
                row['edge_mae']=float(absolute[edge].mean()) if edge.any() else 0.
                row['temporal_error_mae']=float(np.abs(error-previous_error).mean()) if previous_error is not None and not reset else 0.
                previous_error=error
                passed=all(np.isfinite(z).all() for z in (*aligned,*post_motion)) and all(
                    row[n+'_mae']<=1e-6 and row[n+'_max']<=1e-4 for n in ('guide','motion')) and (
                    row['rgb_mae']<=.05 and max(row['eye_changed_over1'])<=.001 and row['edge_mae']<=.20 and row['temporal_error_mae']<=.10)
                row['passed']=bool(passed);report['rows'].append(row)
                if not passed:report['failures'].append(row)
                if index in (1,30):
                    # Shared central crop, same mapping for both eyes and 16x error.
                    y=max(0,h//2-90);x=max(0,w//2-160)
                    tiles=[im[y:y+180,x:x+320] for im in images]
                    diff=np.minimum(absolute[y:y+180,x:x+320]*16,255).astype(np.uint8)
                    cv2.imwrite(str(out/f'{args.model}-{args.tag or "initial"}-{label}-{index}.png'),cv2.cvtColor(np.concatenate((*tiles,diff),axis=1),cv2.COLOR_RGB2BGR))
        print(label,'done',flush=True)

    try:
        if args.public or args.native4k:
            if args.model=='zipdepth':
                from runtime import Engine
            else:
                from screento3d_app.small_gpu_input import SmallGpuCaptureEngine as Engine
                from screento3d_app.desktop_jobs import BUNDLE
                from screento3d_app.resources import configure_resource_root
                from screento3d_app.pipeline import preprocess
                configure_resource_root(BUNDLE)
            with Engine() as engine:
                def infer(rgb):
                    if args.model=='zipdepth':
                        token=engine.infer_device(rgb);engine.complete_device(token)
                        return token.tensor
                    return cv2.resize(engine.infer(preprocess(rgb)).squeeze(),(rgb.shape[1],rgb.shape[0]),interpolation=cv2.INTER_CUBIC)
                for name in (() if args.native4k else ('FloorballGame','OfficeWalk','ParkingGarage')):
                    media=PublicFrames(name,90)
                    def frames():
                        for i in range(90):
                            rgb=media[i]
                            yield rgb,infer(rgb),i==45
                    sequence(name,1920,1080,frames(),True)
                if args.native4k:
                    from hfr_source import CLIP_SHA256,MEDIA
                    for name in ('Jockey','Beauty'):
                        path=MEDIA/f'{name}-120.mp4';assert sha(path)==CLIP_SHA256[name]
                        cap=cv2.VideoCapture(str(path));assert cap.isOpened()
                        try:
                            assert (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))==(3840,2160)
                            assert cap.set(cv2.CAP_PROP_POS_FRAMES,120)
                            def native_frames():
                                for i in range(12):
                                    ok,bgr=cap.read();assert ok
                                    rgb=cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB)
                                    yield rgb,infer(rgb),i==6
                            sequence(name,3840,2160,native_frames(),True,1/120)
                        finally:cap.release()
                else:
                    media=PublicFrames('OfficeWalk',12)
                    def fourk():
                        for i in range(12):
                            rgb=cv2.resize(media[i],(3840,2160))
                            yield rgb,infer(rgb),i==6
                    sequence('Office4K',3840,2160,fourk(),True)
        else:
            for w,h in ((17,19),(257,129),(960,540),(720,1280),(3840,2160)):
                yy,xx=np.indices((h,w));ramp=(xx/max(w-1,1)).astype(np.float32)
                base=rng.integers(0,256,(h,w,3),dtype=np.uint8)
                for pattern in ('flat','dark','low-contrast','thin','step','random'):
                    rgb=base.copy();raw=ramp.copy()
                    if pattern=='flat':rgb[:]=127;raw[:]=.5
                    if pattern=='dark':rgb[:]=rng.integers(0,3,(h,w,3),dtype=np.uint8)
                    if pattern=='low-contrast':rgb[:]=127+(xx%2)[...,None];raw=.5+ramp*1e-6
                    if pattern=='thin':
                        rgb[:]=30;raw[:]=.2
                        for x,width in ((w//4,1),(w//2,2),(3*w//4,8)):
                            rgb[:,x:x+width]=240;raw[:,x:x+width]=.8
                    if pattern=='step':rgb[:,:w//2]=0;rgb[:,w//2:]=255;raw[:,:w//2]=.2;raw[:,w//2:]=.8
                    if pattern=='random':raw=rng.random((h,w),dtype=np.float32)
                    frames=((np.roll(rgb,i,1).copy(),np.roll(raw,i,1).copy(),i==3) for i in range(6))
                    sequence(f'{pattern}-{w}x{h}',w,h,frames,False)
        report['completed']=True;report['passed']=not report['failures']
    finally:target.write_text(json.dumps(report,indent=2))
    print('PASS' if report['passed'] else 'FAIL',len(report['rows']),'frames',len(report['failures']),'failures')
    if not report['passed']:raise SystemExit(1)

if __name__=='__main__':main()
