"""Declared bounded-quality contract for GPU flat-background refinement.

Background membership/eligibility must equal the CPU 4-connected reference.
The 4096-bin median and truncated jump-flood chamfer replace exact CPU median /
two-sweep distance: normalized MAE <=.0003, P99.9 <=.002, max <=.01.
At 4K/strength .5 these bound mean eye displacement below .009 pixels and
maximum below .29 pixels (not a perceptual comfort claim). Bypasses are exact.
"""
import argparse
import ctypes as ct
import json
from pathlib import Path
import time

import cv2
import numpy as np
import torch

from screento3d_app.flat_background_gpu import FlatBackground, color_bounds
from screento3d_app.live_gpu_candidate import DLL_SHA256
from screento3d_app.stereo import refine_flat_background, uniform_color_mask
from uniform_background_tc import generated_frames, load_case, verify_asset


def cpu_background(rgb):
    border=np.concatenate((rgb[0],rgb[-1],rgb[:,0],rgb[:,-1]))
    color=np.median(border,axis=0).astype(np.float32)
    if np.mean(np.max(np.abs(border.astype(np.float32)-color),axis=1)<=.04*255)<.98:
        return color,None
    matching=uniform_color_mask(rgb,color,.04)
    if not .35<=matching.mean()<=.98:return color,None
    _,labels=cv2.connectedComponents(matching.astype(np.uint8),connectivity=4)
    border_labels=np.unique(np.concatenate((labels[0],labels[-1],labels[:,0],labels[:,-1])))
    background=np.isin(labels,border_labels[border_labels!=0])
    return color,background if background.mean()>=.35 else None


def evaluate(rgb,depth,radius,stream):
    h,w=depth.shape
    post=FlatBackground(w,h,int(stream.cuda_stream),DLL_SHA256)
    try:
        post.dll.flat_test.argtypes=[ct.c_void_p]*5+[ct.c_int,ct.c_int,ct.c_float,ct.c_int,ct.POINTER(ct.c_int)]
        color,expected_mask=cpu_background(rgb)
        bounds=color_bounds(color,.04)
        output=np.empty_like(depth);mask=np.zeros(depth.shape,np.uint8);applied=ct.c_int()
        start=time.perf_counter()
        post._check(post.dll.flat_test(post.handle,rgb.ctypes.data,depth.ctypes.data,output.ctypes.data,mask.ctypes.data,
                                      *bounds,.35,radius,ct.byref(applied)))
        elapsed=(time.perf_counter()-start)*1000
        # The production caller performs the uniform-border eligibility check.
        if expected_mask is None:
            assert applied.value != 1
            np.testing.assert_array_equal(output,depth)
            return dict(applied=False,ms=elapsed)
        assert applied.value
        np.testing.assert_array_equal(mask.astype(bool),expected_mask)
        reference=refine_flat_background(rgb,depth,radius=radius)
        error=np.abs(output-reference)
        post.dll.flat_times.argtypes=[ct.c_void_p,ct.c_void_p]
        times=np.zeros(7,np.float32);post._check(post.dll.flat_times(post.handle,times.ctypes.data))
        result=dict(applied=True,mae=float(error.mean()),p999=float(np.quantile(error,.999)),max=float(error.max()),ms=elapsed,gpu_stages_ms=times.tolist())
        assert result['mae']<=.0003 and result['p999']<=.002 and result['max']<=.01,result
        return result
    finally:post.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    stream=torch.cuda.Stream();rows=[];rng=np.random.default_rng(170)
    try:
        frames=list(generated_frames())
        h,w=frames[0].shape[:2]
        holes=frames[0].copy();cv2.rectangle(holes,(80,35),(240,145),(230,100,70),-1)
        cv2.rectangle(holes,(110,60),(180,110),(0,0,0),-1)
        diagonal=np.zeros_like(holes);diagonal[40:120,60:180]=150
        diagonal[np.arange(50,120),np.arange(180,250)]=150
        colored=holes.copy();colored[(colored==0).all(axis=2)]=(17,33,70)
        for name,rgb in [('thin',frames[0]),('holes',holes),('diagonal',diagonal),('colored',colored),
                         ('uniform',np.zeros_like(holes)),('mostly-object',np.full_like(holes,150))]:
            depth=rng.uniform(.1,.9,(h,w)).astype(np.float32)
            for radius in (8,12):rows.append(dict(case=name,size=[w,h],radius=radius,**evaluate(rgb,depth,radius,stream)))
        # Odd widths/partial warps, many disconnected components, enclosed
        # matching islands and low border-connected coverage.
        for w,h in ((17,16),(257,129),(511,255)):
            for probability in (.2,.5,.7):
                mask=rng.random((h,w))<probability
                mask[0]=mask[-1]=False;mask[:,0]=mask[:,-1]=False
                rgb=np.repeat((mask.astype(np.uint8)*150)[:,:,None],3,axis=2)
                depth=rng.uniform(0,1,(h,w)).astype(np.float32)
                rows.append(dict(case=f'components-{probability}',size=[w,h],radius=8,**evaluate(rgb,depth,8,stream)))
        capture=cv2.VideoCapture(str(verify_asset(load_case())))
        for index in (0,30,60,89):
            capture.set(cv2.CAP_PROP_POS_FRAMES,index);ok,bgr=capture.read();assert ok
            for w,h in ((1920,1080),(3840,2160)):
                rgb=np.ascontiguousarray(cv2.cvtColor(cv2.resize(bgr,(w,h)),cv2.COLOR_BGR2RGB))
                yy,xx=np.mgrid[:h,:w].astype(np.float32)
                depth=np.ascontiguousarray(.2+.5*xx/w+.1*np.sin(yy/30))
                for radius in (8,12):rows.append(dict(case=f'flower-{index}',size=[w,h],radius=radius,**evaluate(rgb,depth,radius,stream)))
        capture.release()
    finally:(args.output/'report.json').write_text(json.dumps(dict(rows=rows),indent=2))
    print(json.dumps(dict(passed=True,rows=rows)),flush=True)


if __name__=='__main__':main()
