"""Alternating old-binary/new-mode projection cost; no capture or display claim."""
import argparse
import ctypes as ct
from contextlib import ExitStack
import json
from pathlib import Path
import time

import numpy as np
import torch

from check_stereo_geometry_gpu import load,context,check_cuda
from screento3d_app.desktop_jobs import ROOT
from screento3d_app.live_gpu_candidate import DLL_PATH,DLL_SHA256
from native_path import BRIDGE,BRIDGE_HASH
from tests.test_stereo_geometry import geometry_fixture


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    old=load(ROOT/'out/live-depth-stable/live_depth.dll','5237760648814414a0662330d101a77de3bfa4b6745dd7d6e78026b41c0e1f9b')
    new=load(DLL_PATH,DLL_SHA256)
    bridges=[load(ROOT/'out/vfg-native-bridge-stable/vfg_native_bridge.dll','9ae1c78173ee27e9a3b6e9f81de34fa0e9ed83d9de858ebdd4c91d47f2899114'),load(BRIDGE,BRIDGE_HASH)]
    for lib in (old,new):
        lib.live_set_parallel.argtypes=[ct.c_void_p,ct.c_int]
        lib.live_set_subpixel.argtypes=[ct.c_void_p,ct.c_int]
        lib.live_projection_times.argtypes=[ct.c_void_p,ct.c_void_p]
    new.live_set_coverage.argtypes=[ct.c_void_p,ct.c_int]
    for lib in bridges:
        lib.vfg_project.argtypes=[ct.c_void_p]*2+[ct.c_float]*2+[ct.c_int,ct.c_void_p]
    stream=torch.cuda.Stream()
    rows=[]
    for w,h in ((1920,1080),(3840,2160)):
        with ExitStack() as stack:
            frame,depth=geometry_fixture(w,h)
            handles=[context(stack,lib,frame,depth,stream) for lib in (old,new)]
            for lib,handle in zip((old,new),handles):
                check_cuda(lib.live_set_parallel(handle,1))
                check_cuda(lib.live_set_subpixel(handle,1))
            with torch.cuda.stream(stream):
                pixels=torch.empty((h,w*2,4),dtype=torch.uint8,device='cuda')
            cases=[('old-binary',old,handles[0],bridges[0],None),
                   ('new-subpixel',new,handles[1],bridges[1],0),
                   ('new-coverage',new,handles[1],bridges[1],1)]
            times={name:[] for name,*_ in cases}
            for repeat in range(27):
                for case in [cases[(repeat+i)%3] for i in range(3)]:
                    name,lib,handle,bridge,coverage=case
                    if coverage is not None:
                        check_cuda(new.live_set_coverage(handle,coverage))
                    start=time.perf_counter_ns()
                    assert bridge.vfg_project(handle,pixels.data_ptr(),.45,w*.026*.5,1,None)==1
                    wall=(time.perf_counter_ns()-start)/1e6
                    gpu=np.empty(6,np.float32)
                    check_cuda(lib.live_projection_times(handle,gpu.ctypes.data))
                    if repeat>=6:
                        times[name].append(dict(wall_ms=wall,gpu_ms=float(gpu.sum())))
            rows.append(dict(size=[w,h],median={name:{key:float(np.median([v[key] for v in values])) for key in ('wall_ms','gpu_ms')} for name,values in times.items()}))
    result=dict(passed=True,rows=rows,scope='Alternating synthetic GPU projection into linear RGBA, strength 0.5; includes no VFG generation, capture or Qt')
    args.output.write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
