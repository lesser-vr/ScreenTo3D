# oVDA preprocessing diagnostic, NC-SA-UHDV1.0; see LICENSE/README.md.
"""Bounded CPU threading and GPU prototype measurements; not a product change."""
import argparse
import json
from pathlib import Path
import statistics
import time
import cv2
import numpy as np
import torch
from preprocessing import FramePreprocessor
from screento3d_app.ovda_geometry import select_profile, content_rect
from public_test_media import CORPUS


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    cap=cv2.VideoCapture(str(CORPUS/'FloorballGame.mp4'))
    ok,bgr=cap.read();cap.release()
    if not ok:raise ValueError('Public source unavailable')
    source=cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB)
    original_threads=torch.get_num_threads()
    rows=[]
    try:
        for width,height in ((1920,1080),(3840,2160)):
            frame=np.ascontiguousarray(cv2.resize(source,(width,height)))
            profile=select_profile(width,height)
            pre=FramePreprocessor(profile)
            torch.set_num_threads(original_threads)
            expected=pre.preprocess(frame)
            for threads in sorted({original_threads,1,2,4,8}):
                torch.set_num_threads(threads)
                times=[]
                for i in range(25):
                    start=time.perf_counter();actual=pre.preprocess(frame)
                    if i>=5:times.append((time.perf_counter()-start)*1000)
                assert torch.equal(actual,expected)
                rows.append(dict(size=[width,height],path='CPU',threads=threads,median_ms=statistics.median(times),exact=True))
            mean=pre.mean.cuda();std=pre.std.cuda()
            top,left,h,w=content_rect(width,height,profile)
            def gpu_prepare():
                x=torch.from_numpy(frame.transpose(2,0,1)[None,None]).cuda().float()
                if x.max()>1.0:x=x/255.0
                if (height,width)!=(h,w):
                    x=torch.nn.functional.interpolate(x.flatten(0,1),size=(h,w),mode='bicubic',align_corners=False)[None]
                if (h,w)!=profile:
                    x=torch.nn.functional.pad(x.flatten(0,1),(left,profile[1]-w-left,top,profile[0]-h-top),mode='replicate')[None]
                return ((x-mean)/std).contiguous()
            times=[]
            for i in range(25):
                torch.cuda.synchronize();start=time.perf_counter();actual=gpu_prepare();torch.cuda.synchronize()
                if i>=5:times.append((time.perf_counter()-start)*1000)
            delta=(actual.cpu()-expected).abs()
            rows.append(dict(size=[width,height],path='GPU prototype incl RGB upload + sync',median_ms=statistics.median(times),
                             max_abs=float(delta.max()),mean_abs=float(delta.mean()),
                             note='Prototype tensor comparison only; no depth/cache/SBS quality or capture test'))
    finally:torch.set_num_threads(original_threads)
    result=dict(default_threads=original_threads,rows=rows,
                scope='single public RGB frame; 5 warmups + 20 samples per case; isolated stage, not native FPS')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
