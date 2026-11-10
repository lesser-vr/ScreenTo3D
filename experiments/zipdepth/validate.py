"""GPU preprocessing/reference and ownership checks for the experiment adapter."""
import json
from pathlib import Path
import sys
import threading
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'v1'),str(ROOT/'out/zipdepth-upstream')]
import cv2
import numpy as np
import torch
from runtime import Engine,rect,SHAPE
from public_test_media import PublicFrames
from zipdepth.model.architecture import create_model
from zipdepth.utils.model_utils import strip_state_dict_prefixes

def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT/'out/zipdepth-adapter-validation.json')
    args=parser.parse_args()
    torch.set_num_threads(4)
    model=create_model(variant='base').eval()
    checkpoint=torch.load(ROOT/'out/zipdepth-upstream/checkpoints/zipdepth_base.pth',map_location='cpu',weights_only=True)
    model.load_state_dict(strip_state_dict_prefixes(checkpoint.get('model_state_dict',checkpoint)),strict=True)
    rgb=PublicFrames('OfficeWalk',1)[0]
    rows=[]
    with Engine() as engine:
        prior=None
        for width,height in ((1920,1080),(1000,1000),(720,1280),(3440,1440)):
            image=cv2.resize(rgb,(width,height))
            y,x,h,w=rect(width,height)
            ref=cv2.resize(image,(w,h),interpolation=cv2.INTER_LINEAR)
            ref=cv2.copyMakeBorder(ref,y,SHAPE[0]-h-y,x,SHAPE[1]-w-x,cv2.BORDER_REPLICATE)
            inp=torch.from_numpy(np.ascontiguousarray(ref.transpose(2,0,1)[None],dtype=np.float32)/255)
            with torch.inference_mode():
                expected=model(inp)[:,:,y:y+h,x:x+w]
                expected=torch.nn.functional.interpolate(expected,(height,width),mode='bilinear',align_corners=True)[0,0].numpy()
            token=engine.infer_device(image)
            if prior is not None:
                expired=False
                try:prior.validate()
                except ValueError:expired=True
                assert expired
            assert tuple(token.tensor.shape)==(1,height,width)
            actual=token.tensor.cpu().numpy()[0]
            blocked=False
            try:engine.infer_device(image)
            except RuntimeError:blocked=True
            assert blocked
            engine.complete_device(token)
            token.validate()  # Exact-RGB reuse stays valid until the next inference.
            engine.complete_device(token)
            prior=token
            diff=np.abs(actual-expected)
            span=max(float(np.percentile(expected,99)-np.percentile(expected,1)),1e-6)
            row=dict(width=width,height=height,rect=[y,x,h,w],mae=float(diff.mean()),
                     span_normalized_mae=float(diff.mean()/span),max=float(diff.max()))
            assert row['span_normalized_mae']<.01
            rows.append(row)
        errors=[]
        def wrong_thread():
            try:engine._check()
            except RuntimeError:errors.append('rejected')
        thread=threading.Thread(target=wrong_thread);thread.start();thread.join()
        assert errors==['rejected']
    closed=False
    try:engine._check()
    except RuntimeError:closed=True
    assert closed
    args.output.write_text(json.dumps(dict(success=True,
        scope='FP16 plus GPU uint8 bilinear preprocessing versus original FP32 OpenCV reference; 1% depth-span MAE bound, not a visual quality threshold',
        cases=rows,ownership=True,reuse_after_completion=True,expired_after_new_inference=True,close=True),indent=2))
if __name__=='__main__':main()
