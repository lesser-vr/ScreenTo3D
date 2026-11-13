"""Compare a retained native SBS texture with always rendering identical DA2 tokens."""
import argparse
from contextlib import ExitStack
import ctypes as ct
import json
import os
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from check_da2_radius8 import BUILDS, Build, renderer
from screento3d_app import live_gpu_candidate, live_texture_pool, small_gpu_input
from screento3d_app.da2_base import binding
from screento3d_app.desktop_jobs import BUNDLE, ROOT
from screento3d_app.live_policy import StaticSbsReuse, same_rgb
from screento3d_app.resources import configure_resource_root
from screento3d_app.trt_backend import DepthEngine
from public_test_media import PublicFrames


def compare(mode,runtime):
    w,h=1280,720
    frames=[cv2.resize(f,(w,h),interpolation=cv2.INTER_AREA) for f in PublicFrames('FloorballGame',8)]
    base=frames[0]
    pixel=base.copy()
    pixel[101,203]^=255
    assert np.array_equal(cv2.resize(base,(32,32)),cv2.resize(pixel,(32,32)))
    resume=135+24
    inputs=[base]*135+[pixel]*24+frames+[frames[-1]]*480
    held=held_after_motion=0
    max_error=changed=legacy_max=legacy_changed=0
    flags={}
    previous=None
    with ExitStack() as stack:
        if mode=='balanced':
            backend=binding(ROOT/'out/da2-base-local',runtime,device_depth=True)
            backend.input_validator(dict(width=w,height=h))
            engine=stack.enter_context(backend.engine_factory(None))
        else:
            engine=stack.enter_context(DepthEngine())
        product=Build('static-sbs',live_gpu_candidate.DLL_SHA256,small_gpu_input.DLL_SHA256,
                      live_texture_pool.RUNTIME_SHA256)
        legacy,reference,trial=[renderer(stack,build,mode,engine,w,h) for build in (BUILDS[1],product,product)]
        state=StaticSbsReuse()
        def probe(handle,compare):
            reason=ct.c_int()
            m=trial.motion_history
            m._check(m.dll.motion_static_probe(m.handle,handle,int(compare),ct.byref(reason)))
            flags[reason.value]=flags.get(reason.value,0)+1
            return reason.value
        stack.enter_context(patch.object(trial.motion_history,'static_probe',probe))
        images=[np.empty((h,w*2,4),np.uint8) for _ in range(3)]
        for i,frame in enumerate(inputs):
            legacy.source_ns=reference.source_ns=trial.source_ns=1_000_000_000+round(i*1e9/60)
            token=reference.infer(frame)
            scene=trial.inspect_scene(frame)
            hold=state.hold(previous is not None and not scene.cut and same_rgb(frame,previous),trial.source_ns)
            with patch.object(engine,'complete_device',lambda t:t.validate()):
                legacy.render(frame,token)
                reference.set_same_input(state.stationary)
                reference.render(frame,token)
            reference.pool.check(reference.pool.dll.live_pool_readback(reference.pool.handle,0,images[0].ctypes.data))
            legacy.pool.check(legacy.pool.dll.live_pool_readback(legacy.pool.handle,0,images[2].ctypes.data))
            if hold:
                trial.hold_static(scene)
                engine.complete_device(token)
                held+=1
                if i>=resume+len(frames):
                    held_after_motion+=1
            else:
                trial.set_same_input(state.stationary)
                trial.render(frame,token,scene=scene)
                state.after_render(trial,trial.source_ns)
                trial.pool.check(trial.pool.dll.live_pool_readback(trial.pool.handle,0,images[1].ctypes.data))
            if i==135:
                assert not hold
            error=cv2.absdiff(images[0],images[1])
            changed+=int(np.count_nonzero(error))
            max_error=max(max_error,int(error.max()))
            difference=cv2.absdiff(images[1],images[2])
            legacy_changed+=int(np.count_nonzero(difference))
            legacy_max=max(legacy_max,int(difference.max()))
            previous=frame
    return dict(mode=mode,frames=len(inputs),held=held,held_after_motion=held_after_motion,
                changed_channels=changed,max_error=max_error,
                legacy_changed_channels=legacy_changed,legacy_max=legacy_max,probe_flags=flags)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    configure_resource_root(BUNDLE)
    runtime=Path('C:/TensorRT/TensorRT-11.2.1.2/bin')
    with os.add_dll_directory(str(runtime)):
        for mode in ('balanced','performance'):
            result=compare(mode,runtime)
            print(json.dumps(result),flush=True)
            (args.output/f'{mode}.json').write_text(json.dumps(result,indent=2))
            assert result['held_after_motion'] and result['changed_channels']==0


if __name__=='__main__':
    main()
