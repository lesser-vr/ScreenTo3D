# oVDA input adaptation validation, NC-SA-UHDV1.0; see LICENSE/README.md.
"""Bounded GPU tensor, cache, depth and native SBS comparisons on public inputs."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import threading
from unittest.mock import patch
import cv2
import numpy as np
import torch
from depthsbs_app import ovda
from depthsbs_app.desktop_jobs import ROOT
from depthsbs_app.gpu_frame import GpuFrame
from depthsbs_app.ovda_geometry import CANVASES, SUPPORTED_CANVASES, select_profile
from public_test_media import CORPUS


class InputOwner:
    def __init__(self):
        self.torch=torch;self.device=torch.cuda.current_device()
        self.stream=torch.cuda.Stream();self.owner=threading.get_ident();self.closed=False
        from _depthsbs_ovda.gpu_input import OvdaGpuInput
        self.gpu_input=OvdaGpuInput(self)
    def _check(self):
        if self.closed or threading.get_ident()!=self.owner or torch.cuda.current_device()!=self.device:
            raise RuntimeError('Closed or foreign input owner')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--preprocess-only',action='store_true')
    parser.add_argument('--reference-runtime',action='store_true')
    parser.add_argument('--include-resolution-trial',action='store_true')
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    cls=ovda.runtime_class(True)
    from _depthsbs_ovda.preprocessing import FramePreprocessor
    cap=cv2.VideoCapture(str(CORPUS/'FloorballGame.mp4'))
    ok,bgr=cap.read();cap.release()
    if not ok:raise ValueError('Missing public source')
    source=cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB)
    report=dict(preprocessing=[],sequences=[],rejections=[],scope='explicit tensor/depth/cache/native readbacks; not live FPS')
    owner=InputOwner()
    try:
        def rejected(name,error,operation):
            try:operation()
            except error:report['rejections'].append(name)
            else:raise AssertionError('Missing rejection: '+name)
        from _depthsbs_ovda import gpu_input as native_input
        with patch.object(native_input,'DLL_SHA256','0'*64):
            rejected('DLL checksum',ValueError,lambda:native_input.OvdaGpuInput(owner))
        with torch.cuda.stream(owner.stream):
            image=torch.zeros((16,16,3),dtype=torch.uint8,device=owner.device)
            rejected('invalid dtype',ValueError,lambda:owner.gpu_input.prepare(image.float(),(518,924)))
            rejected('invalid canvas',ValueError,lambda:owner.gpu_input.prepare(image,(518,518)))
            rejected('invalid image size',ValueError,lambda:owner.gpu_input.prepare(image[:8],(518,924)))
        rejected('foreign current stream',RuntimeError,lambda:owner.gpu_input.prepare(image,(518,924)))
        errors=[]
        def foreign_thread():
            try:owner.gpu_input.execution.check()
            except RuntimeError:errors.append(True)
        thread=threading.Thread(target=foreign_thread);thread.start();thread.join()
        assert errors==[True]
        report['rejections'].append('foreign thread')
        for shape in (SUPPORTED_CANVASES if args.include_resolution_trial else CANVASES):
            for w,h in ((1920,1080),(3840,2160),(3440,1440),(1080,1920),(1024,1024),(1056,608),(shape[1],shape[0]),(16,16)):
                public=np.ascontiguousarray(cv2.resize(source,(w,h)))
                rng=np.random.default_rng(321)
                for name,rgb in (('public',public),('zero',np.zeros_like(public)),('one',np.ones_like(public)),
                                 ('binary',rng.integers(0,2,public.shape,dtype=np.uint8)),
                                 ('random',rng.integers(0,256,public.shape,dtype=np.uint8))):
                    bgra=cv2.cvtColor(rgb,cv2.COLOR_RGB2BGRA)
                    # Alpha must not change the max<=1 rule. Exercise pitched BGRA too.
                    with torch.cuda.stream(owner.stream):
                        device=torch.from_numpy(bgra).to(owner.device)
                        frame=GpuFrame(device,owner)
                        a=owner.gpu_input.prepare(frame.rgb,shape).unsqueeze(1).cpu()
                        padded=torch.empty((h,w+7,4),dtype=torch.uint8,device=owner.device)
                        pitched=padded[:,:w];pitched.copy_(device)
                        b=owner.gpu_input.prepare(pitched,shape).unsqueeze(1).cpu()
                    expected=FramePreprocessor(shape).preprocess(rgb)
                    delta=(a-expected).abs()
                    maximum=float(delta.max())
                    np.testing.assert_allclose(a.numpy(),expected.numpy(),atol=1e-5,rtol=0)
                    assert torch.equal(a,b)
                    assert frame.readback_bytes==0
                    report['preprocessing'].append(dict(size=[w,h],canvas=shape,pattern=name,max_abs=maximum,
                                                         mean_abs=float(delta.mean()),rgb_bgra_exact=True))
            print('PREPROCESS PASS',shape,flush=True)
    finally:
        owner.stream.synchronize();owner.closed=True
        (args.output/'report.json').write_text(json.dumps(report,indent=2))
    if not args.preprocess_only:
        from depthsbs_app.live_policy import resolve_live
        from depthsbs_app.live_source_gpu_texture import LiveSourceGpuTexture
        profiles=ovda.profiles(ROOT/'out/ovda-local')
        policy=replace(resolve_live('video-quality',.5),stereo_layout='half-tb')
        for w,h,count in ((1280,720,20),(3840,2160,18),(3440,1440,18),(1080,1920,18),(1024,1024,18),(1056,608,18)):
            shape=select_profile(w,h,profiles)
            from runtime_trial import reference_class
            reference=reference_class() if args.reference_runtime else cls
            host=reference(directory=profiles[shape],profile=shape)
            gpu=cls(directory=profiles[shape],profile=shape)
            posts=[]
            row=dict(size=[w,h],canvas=shape,frames=0,depth_max_abs=0.,cache_max_abs=0.,sbs_max_abs=0,sbs_mae_max=0.)
            try:
                posts=[LiveSourceGpuTexture(w,h,policy,engine,diagnostic=True) for engine in (host,gpu)]
                for clip in ('FloorballGame','OfficeWalk','ParkingGarage'):
                    host.reset('scene_cut');gpu.reset('scene_cut')
                    for post in posts:post.reset()
                    cap=cv2.VideoCapture(str(CORPUS/(clip+'.mp4')))
                    try:
                        for index in range(count):
                            ok,bgr=cap.read()
                            if not ok:raise ValueError('Short public clip')
                            rgb=np.ascontiguousarray(cv2.resize(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB),(w,h)))
                            with torch.cuda.stream(gpu.stream):
                                frame=GpuFrame(torch.from_numpy(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGRA)).to(gpu.device),gpu)
                            reference_frame=rgb
                            if args.reference_runtime:
                                with torch.cuda.stream(host.stream):
                                    reference_frame=GpuFrame(torch.from_numpy(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGRA)).to(host.device),host)
                            a,b=posts[0].infer(reference_frame),posts[1].infer(frame)
                            if index==0:
                                rejected('pending reset',RuntimeError,lambda:gpu.reset('scene_cut'))
                                rejected('pending inference',RuntimeError,lambda:gpu.infer_device(frame))
                                rejected('foreign token',ValueError,lambda:host.complete_device(b))
                            host.stream.synchronize();gpu.stream.synchronize()
                            da,db=a.tensor.cpu().numpy(),b.tensor.cpu().numpy()
                            np.testing.assert_allclose(db,da,atol=.001,rtol=.001)
                            row['depth_max_abs']=max(row['depth_max_abs'],float(np.abs(db-da).max()))
                            for key in host.cache if index in (0,15,count-1) else ():
                                ca,cb=host.cache[key].cpu().numpy(),gpu.cache[key].cpu().numpy()
                                np.testing.assert_allclose(cb,ca,atol=.001,rtol=.001)
                                row['cache_max_abs']=max(row['cache_max_abs'],float(np.abs(cb-ca).max()))
                            assert gpu.last_input_bytes==0 and frame.readback_bytes==0
                            # Actual native texture synthesis and readback, then complete owned tokens.
                            outputs=[]
                            from depthsbs_app.stereo_layout import dimensions
                            ow,oh=dimensions(w,h,policy.stereo_layout)
                            for post,original,token in zip(posts,(reference_frame,frame),(a,b)):
                                post.slot=index%2
                                slot=post.render(original,token)
                                result=np.empty((oh,ow,4),np.uint8)
                                post.pool.check(post.pool.dll.live_pool_readback(post.pool.handle,slot,result.ctypes.data))
                                assert np.all(result[:,:,3]==255)
                                outputs.append(result[:,:,:3].copy())
                            if index==0:rejected('completed token',RuntimeError,b.validate)
                            diff=np.abs(outputs[0].astype(np.int16)-outputs[1].astype(np.int16))
                            row['sbs_max_abs']=max(row['sbs_max_abs'],int(diff.max()))
                            row['sbs_mae_max']=max(row['sbs_mae_max'],float(diff.mean()))
                            assert float(diff.mean())<=.1 and float(np.mean(np.any(diff>8,axis=2)))<=.005
                            row['frames']+=1
                    finally:cap.release()
                report['sequences'].append(row)
                print('SEQUENCE PASS',json.dumps(row),flush=True)
            finally:
                for post in reversed(posts):post.close()
                host.close();gpu.close()
                (args.output/'report.json').write_text(json.dumps(report,indent=2))
    report['passed']=True
    (args.output/'report.json').write_text(json.dumps(report,indent=2))


if __name__=='__main__':main()
