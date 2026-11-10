"""Analytic area-coverage oracle for near/far silhouettes, not depth estimation."""
import argparse
import ctypes as ct
from contextlib import ExitStack
import json
from pathlib import Path

import numpy as np
import torch

from check_stereo_geometry_gpu import load,context,check_cuda
from check_stereo_stability_gpu import project
from depthsbs_app.live_gpu_candidate import DLL_PATH,DLL_SHA256


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--dll',type=Path,default=DLL_PATH)
    parser.add_argument('--sha256',default=DLL_SHA256)
    args=parser.parse_args()
    dll=load(args.dll,args.sha256)
    dll.live_set_subpixel.argtypes=[ct.c_void_p,ct.c_int]
    dll.live_set_coverage.argtypes=[ct.c_void_p,ct.c_int]
    stream=torch.cuda.Stream()
    x=np.arange(1920,dtype=np.float64)
    rows=[]
    for strength in (.25,.5,1.,2.):
        for thickness in (1,2,7,500):
            frame=np.zeros((16,1920,3),np.uint8)
            frame[:,:,2]=255
            frame[:,700:700+thickness]=(255,0,0)
            depth=np.full(frame.shape[:2],.05,np.float32)
            errors={0:[],1:[]}
            steps={0:[],1:[]}
            old_alpha={0:None,1:None}
            with ExitStack() as stack:
                handle=context(stack,dll,frame,depth,stream)
                check_cuda(dll.live_set_subpixel(handle,1))
                shifts=sorted(set(np.linspace(10*strength-.2,10*strength+.2,81)) |
                              {10*strength+offset for offset in (-1e-4,-1e-5,-1e-6,-1e-7,1e-7,1e-6,1e-5,1e-4)})
                for shift in shifts:
                    scale=1920*.026*strength
                    depth[:,700:700+thickness]=.45+2*shift/scale
                    analytic=np.stack([np.clip(np.minimum(x+.5,700+thickness-.5+sign*shift)-
                                                np.maximum(x-.5,700-.5+sign*shift),0,1)
                                       for sign in (1,-1)])
                    for enabled in (0,1):
                        check_cuda(dll.live_set_coverage(handle,enabled))
                        result=project(dll,handle,frame,depth,.45,scale)
                        alpha=result[8,:,0].reshape(2,1920).astype(float)/255
                        errors[enabled].append(float(np.max(np.abs(alpha-analytic))))
                        if old_alpha[enabled] is not None:
                            steps[enabled].append(float(np.max(np.abs(alpha-old_alpha[enabled]))))
                        old_alpha[enabled]=alpha
                        if enabled:
                            assert np.max(np.abs(alpha-analytic))<=1.1/255,(strength,thickness,shift,errors[enabled][-1])
                            assert np.max(np.abs(alpha.sum(axis=1)-thickness))<=2.1/255
                            # Mixing is permitted only in analytically partial pixels.
                            mixed=(alpha>0)&(alpha<1)
                            assert np.all((analytic[mixed]>0)&(analytic[mixed]<1))
                            assert np.max(np.abs(result[8,:,2].astype(int)+result[8,:,0].astype(int)-255))<=1
                assert max(steps[1])<=2.1/255
                rows.append(dict(strength=strength,thickness=thickness,
                    old_alpha_max_error=max(errors[0]),coverage_alpha_max_error=max(errors[1]),
                    old_max_frame_alpha_step=max(steps[0]),coverage_max_frame_alpha_step=max(steps[1])))
    # Stable coordinate arithmetic may change a rounding tie by one RGB level.
    frame=np.random.default_rng(9).integers(0,256,(32,1920,3),np.uint8)
    depth=np.broadcast_to(np.linspace(.1,.9,1920,dtype=np.float32),(32,1920)).copy()
    with ExitStack() as stack:
        handle=context(stack,dll,frame,depth,stream)
        check_cuda(dll.live_set_subpixel(handle,1))
        check_cuda(dll.live_set_coverage(handle,0))
        before=project(dll,handle,frame,depth,.45,24.96)
        check_cuda(dll.live_set_coverage(handle,1))
        after=project(dll,handle,frame,depth,.45,24.96)
        smooth_error=int(np.abs(before.astype(np.int16)-after.astype(np.int16)).max())
        assert smooth_error<=1
        identity=project(dll,handle,frame,depth,.45,0)
        assert np.array_equal(identity,np.concatenate((frame,frame),axis=1))
        depth[:]=.6
        plane_error=0
        for shift in (.01,.1,.49,.5,.99,1.,1.01):
            result=project(dll,handle,frame,depth,.6-2*shift/24.96,24.96)
            for eye,sign in ((0,1),(1,-1)):
                expected=np.stack([np.interp(x-sign*shift,x,frame[8,:,channel]) for channel in range(3)],axis=1)
                expected=np.floor(expected+.5).astype(np.uint8)
                error=int(np.abs(result[8,eye*1920+10:(eye+1)*1920-10].astype(np.int16)-expected[10:-10].astype(np.int16)).max())
                plane_error=max(plane_error,error)
        assert plane_error<=1
    result=dict(passed=True,dll_sha256=args.sha256,rows=rows,smooth_surface_max_rgb_error=smooth_error,
                analytic_textured_plane_max_rgb_error=plane_error,zero_disparity_exact=True,
                scope='Constant-color two-layer analytic coverage, both eyes; not general occlusion or viewing acceptance')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
