"""Real-engine learned renderer contract: identical compiled host/native pixels."""
import argparse
from contextlib import ExitStack
from dataclasses import replace
import json
import os
from pathlib import Path

import cv2
import numpy as np

from depthsbs_app.da2_base import binding
from depthsbs_app.desktop_jobs import ROOT,BUNDLE
from depthsbs_app.resources import configure_resource_root
from depthsbs_app.live_policy import resolve_live
from depthsbs_app.rowflow import RowFlowRenderer


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--sizes',default='1920x1080,3840x2160,1080x1920,3440x1440')
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    configure_resource_root(BUNDLE)
    image=cv2.cvtColor(cv2.imread(str(ROOT/'out/iw3-render-comparison-calibrated-20261105/OfficeWalk/source.png')),cv2.COLOR_BGR2RGB)
    rows=[]
    for size in args.sizes.split(','):
        w,h=map(int,size.split('x'))
        with ExitStack() as stack:
            runtime=Path('C:/TensorRT/TensorRT-11.2.1.2/bin')
            stack.enter_context(os.add_dll_directory(str(runtime)))
            b=binding(ROOT/'out/da2-base-local',runtime,device_depth=True)
            b.input_validator(dict(width=w,height=h));engine=stack.enter_context(b.engine_factory(None))
            renderer=stack.enter_context(RowFlowRenderer(w,h,replace(resolve_live('balanced'),depth_backend='da2-base'),engine,native=True,diagnostic=True))
            readback=np.empty((h,w*2,4),np.uint8)
            for index in range(3):
                rgb=cv2.resize(image,(w,h))
                if index==1:rgb=255-rgb
                if index==2:
                    rgb[:]=112
                    cv2.rectangle(rgb,(w//3,h//3),(w*2//3,h*2//3),(180,80,50),-1)
                from depthsbs_app.gpu_frame import GpuFrame
                with engine.torch.cuda.stream(engine.stream):
                    frame=GpuFrame(engine.torch.from_numpy(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGRA)).cuda(),engine)
                token=renderer.infer(frame)
                renderer.slot=index%2
                slot=renderer.render(frame,token)
                renderer.pool.check(renderer.pool.dll.live_pool_readback(renderer.pool.handle,slot,readback.ctypes.data))
                with engine.torch.inference_mode(),engine.torch.cuda.stream(engine.stream):
                    expected=renderer._render_pixels().cpu().numpy()
                    eager=renderer._render_pixels(compiled=False).cpu().numpy()
                assert np.array_equal(readback[:,:,:3],expected) and np.all(readback[:,:,3]==255)
                assert engine.pending_device is None
                difference=np.abs(expected.astype(np.int16)-eager.astype(np.int16))
                row=dict(size=size,frame=index,native_host_exact=True,raw_token_completed=True,
                    eager_mae=float(difference.mean()),eager_max=int(difference.max()),render_ms=renderer.rowflow_ms)
                rows.append(row);print(json.dumps(row),flush=True)
                if index==0:
                    cv2.imwrite(str(args.output/(size+'-rowflow.png')),cv2.cvtColor(expected,cv2.COLOR_RGB2BGR))
            # Nonfinite output must fail without stale success.
            with engine.torch.inference_mode(),engine.torch.cuda.stream(engine.stream):renderer.aligned.fill_(float('nan'))
            try:
                with engine.torch.inference_mode(),engine.torch.cuda.stream(engine.stream):renderer._render_pixels()
            except ValueError:pass
            else:raise AssertionError('Nonfinite output accepted')
    (args.output/'report.json').write_text(json.dumps(dict(passed=True,rows=rows),indent=2))


if __name__=='__main__':main()
