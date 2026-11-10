"""Same fresh Base FP16 depth for old/new coverage, with public preview artifacts."""
import argparse
import ctypes as ct
from contextlib import ExitStack
import json
import os
from pathlib import Path

import cv2
import numpy as np
import torch

from check_stereo_geometry_gpu import load,check_cuda
from depthsbs_app.da2_base import binding
from depthsbs_app.desktop_jobs import ROOT
from depthsbs_app.live_gpu_candidate import DLL_PATH,DLL_SHA256
from depthsbs_app.live_policy import resolve_live
from depthsbs_app.live_scene_history import LiveSceneHistory
from public_test_media import PublicFrames,SOURCES,ATTRIBUTION


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    cv2.setNumThreads(1)
    torch.set_num_threads(4)
    dll=load(DLL_PATH,DLL_SHA256)
    prior=load(ROOT/'out/live-depth-stable/live_depth.dll',
               '5237760648814414a0662330d101a77de3bfa4b6745dd7d6e78026b41c0e1f9b')
    dll.live_set_coverage.argtypes=[ct.c_void_p,ct.c_int]
    for library in (dll,prior):
        library.live_set_subpixel.argtypes=[ct.c_void_p,ct.c_int]
        library.live_set_parallel.argtypes=[ct.c_void_p,ct.c_int]
    policy=resolve_live('balanced',.5)
    result=dict(passed=False,strength=.5,clips=[],attribution=ATTRIBUTION,
        scope='Public 1080p Base FP16, identical raw depth, CUDA postprocessing; bypasses optional flat-border refinement; no physical stereo review')
    with ExitStack() as stack:
        runtime=Path('C:/TensorRT/TensorRT-11.2.1.2/bin')
        stack.enter_context(os.add_dll_directory(str(runtime)))
        backend=binding(ROOT/'out/da2-base-local',runtime)
        backend.input_validator(dict(width=1920,height=1080))
        engine=stack.enter_context(backend.engine_factory(None))
        for name in SOURCES:
            with ExitStack() as owned:
                handles=[]
                for library in (prior,dll):
                    handle=ct.c_void_p()
                    check_cuda(library.live_create(ct.byref(handle),1920,1080,engine.stream.cuda_stream))
                    owned.callback(lambda lib=library,h=handle:check_cuda(lib.live_destroy(h)))
                    check_cuda(library.live_set_subpixel(handle,1))
                    check_cuda(library.live_set_parallel(handle,1))
                    handles.append(handle)
                movie=args.output/f'{name}-left-eye-crop.mp4'
                writer=cv2.VideoWriter(str(movie),cv2.VideoWriter_fourcc(*'mp4v'),30,(1920,720))
                assert writer.isOpened()
                owned.callback(writer.release)
                history=LiveSceneHistory(policy.scene_cut_threshold)
                rows=[]
                best=(-1,None)
                for index,rgb in enumerate(PublicFrames(name,180)):
                    if index%2:
                        continue
                    raw=np.ascontiguousarray(engine.infer(rgb)[0])
                    scene=history.inspect(rgb)
                    outputs=[]
                    for library,handle in zip((prior,dll),handles):
                        check_cuda(library.live_post_source(handle,rgb.ctypes.data,raw.ctypes.data,0,
                            policy.depth_guide_radius,policy.temporal_alpha,policy.temporal_color_threshold,
                            policy.temporal_depth_threshold,int(index==0 or scene.cut),None,policy.temporal_depth_transition))
                        # Keep the aligned depth on its owned GPU context.
                        left,right=np.empty_like(rgb),np.empty_like(rgb)
                        invalid=ct.c_int()
                        if library is dll:
                            check_cuda(dll.live_set_coverage(handle,0))
                        check_cuda(library.live_project(handle,None,policy.convergence,1920*policy.divergence,1,
                            left.ctypes.data,right.ctypes.data,ct.byref(invalid)))
                        assert not invalid.value
                        outputs.append(np.concatenate((left,right),axis=1))
                    assert np.array_equal(*outputs),'Old subpixel mode changed'
                    check_cuda(dll.live_set_coverage(handles[1],1))
                    check_cuda(dll.live_project(handles[1],None,policy.convergence,1920*policy.divergence,1,
                        left.ctypes.data,right.ctypes.data,ct.byref(invalid)))
                    assert not invalid.value
                    improved=np.concatenate((left,right),axis=1)
                    difference=np.max(np.abs(improved.astype(np.int16)-outputs[0].astype(np.int16)),axis=2)
                    crop=np.concatenate((outputs[0][180:900,480:1440],improved[180:900,480:1440]),axis=1)
                    bgr=cv2.cvtColor(crop,cv2.COLOR_RGB2BGR)
                    cv2.putText(bgr,'Previous / Coverage | strength 0.5',(18,34),cv2.FONT_HERSHEY_SIMPLEX,.8,(255,255,255),2)
                    writer.write(bgr)
                    row=dict(index=index,reference_exact=True,max_rgb_delta=int(difference.max()),
                             over1_fraction=float(np.mean(difference>1)),mean_pixel_max_delta=float(difference.mean()))
                    rows.append(row)
                    if row['over1_fraction']>best[0]:
                        best=(row['over1_fraction'],bgr.copy())
                    history.commit(scene)
                writer.release()
                capture=cv2.VideoCapture(str(movie))
                count=0
                while capture.read()[0]:
                    count+=1
                capture.release()
                assert count==90
                assert cv2.imwrite(str(args.output/f'{name}-largest-change.png'),best[1])
                summary=dict(clip=name,frames=count,reference_exact=True,
                    mean_over1_fraction=float(np.mean([r['over1_fraction'] for r in rows])),
                    max_over1_fraction=max(r['over1_fraction'] for r in rows))
                result['clips'].append(dict(**summary,rows=rows))
                print(json.dumps(summary),flush=True)
    result['passed']=True
    (args.output/'result.json').write_text(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
