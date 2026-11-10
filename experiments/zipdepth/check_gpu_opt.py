"""Exact matched-depth/native SBS parity against the previous pinned binaries."""
import ctypes as ct
from contextlib import ExitStack
import hashlib,json
from pathlib import Path
import sys,time
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'v1'))

def main():
    import cv2,numpy as np,torch
    from check_stereo_geometry_gpu import load,context,check_cuda,texture
    from check_stereo_detail import setup
    from check_stereo_window import settings
    from depthsbs_app.live_texture_pool import LiveTexturePool
    from public_test_media import PublicFrames
    from depthsbs_app import rowflow
    borrowed=rowflow.bridge()
    out=ROOT/'out/gpu-load-opt'
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    old_path=ROOT/'out/live-depth-detail/live_depth.dll'
    old=setup(old_path,'a712b91082de8e31fb7c35ab81cae51c5c4d6a1d31b014b486be410646516c40')
    new=setup(out/'live_depth.dll',sha(out/'live_depth.dll'))
    class OldPool(LiveTexturePool):
        library_path=ROOT/'out/live-texture-detail/live_texture_runtime.dll'
        library_sha256='5a044937a451184f4d3b2aa45bdd01504f41f9cdb8bd89016aac85d0ea4eb08e'
    class NewPool(LiveTexturePool):
        library_path=out/'live_texture_runtime.dll'
        library_sha256=sha(library_path)
    rng=np.random.default_rng(20261106);stream=torch.cuda.Stream()
    report=dict(completed=False,contract='Exact float32 aligned depth and byte-identical native RGBA, same inputs/history',rows=[])
    try:
        for w,h in ((17,19),(257,129),(1920,1080),(960,960),(720,1280),(3840,2160)):
            rgb=cv2.resize(PublicFrames('OfficeWalk',1)[0],(w,h))
            raw=rng.random((h,w),dtype=np.float32)
            with ExitStack() as stack:
                handles=[context(stack,lib,rgb,raw,stream) for lib in (old,new)]
                pools=[stack.enter_context(cls(w,h,diagnostic=True)) for cls in (OldPool,NewPool)]
                for lib,handle in zip((old,new),handles):
                    settings(lib,handle)
                    check_cuda(lib.live_set_disparity_budget(handle,1));check_cuda(lib.live_set_detail(handle,3))
                for index in range(8):
                    if index==2:raw.fill(.5)
                    if index==4:raw=rng.random((h,w),dtype=np.float32)*1e-6
                    if index==6:raw[:,w//2:]+=1
                    frame=np.roll(rgb,index,axis=1).copy(); outputs=[];depths=[];times=[]
                    with torch.cuda.stream(stream):
                        drgb=torch.from_numpy(frame).cuda();draw=torch.from_numpy(raw).cuda()
                    for lib,handle,pool in zip((old,new),handles,pools):
                        depth=np.empty_like(raw);begin=time.perf_counter_ns()
                        check_cuda(lib.live_set_range_dt(handle,1/60))
                        check_cuda(lib.live_set_window(handle,1/60,int(index==0)))
                        check_cuda(lib.live_post_source(handle,drgb.data_ptr(),draw.data_ptr(),2,4,.55,.04,.08,int(index in (0,4)),depth.ctypes.data,.008))
                        stream.synchronize();times.append((time.perf_counter_ns()-begin)/1e6)
                        if lib is new and index==0:
                            with torch.cuda.stream(stream):
                                borrowed_rgb=torch.empty_like(drgb);borrowed_depth=torch.empty_like(draw)
                            invalid=ct.c_int()
                            rowflow.check(borrowed,borrowed.rowflow_copy_inputs(handle,borrowed_rgb.data_ptr(),
                                borrowed_depth.data_ptr(),None,ct.byref(invalid)))
                            assert not invalid.value
                            assert np.array_equal(borrowed_rgb.cpu().numpy(),frame)
                            assert np.array_equal(borrowed_depth.cpu().numpy(),depth)
                        outputs.append(texture(pool,handle,w*.026*.25));depths.append(depth)
                    assert np.array_equal(depths[0],depths[1]),(w,h,index,'depth',float(np.max(np.abs(depths[0]-depths[1]))))
                    assert np.array_equal(outputs[0],outputs[1]),(w,h,index,'RGBA')
                    report['rows'].append(dict(size=[w,h],index=index,exact=True,post_diagnostic_ms=times))
        report['completed']=True
    except BaseException as exc:report['error']=repr(exc);raise
    finally:(out/'parity.json').write_text(json.dumps(report,indent=2))

if __name__=='__main__':main()
