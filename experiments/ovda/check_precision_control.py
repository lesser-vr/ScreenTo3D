# oVDA precision control, NC-SA-UHDV1.0; see LICENSE/README.md.
"""Check the fresh FP32 control and quantify per-frame raw depth differences."""
import argparse
import json
from pathlib import Path
import statistics
import cv2
import numpy as np
import torch
from trial_runtime import create_engine
from public_test_media import CORPUS


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    engines={v:create_engine(v) for v in ('fp32','fp32-current','encoder','encoder-spatial')}
    rows=[];strict=True
    try:
        for clip in ('FloorballGame','OfficeWalk','ParkingGarage'):
            for engine in engines.values():engine.reset('start')
            cap=cv2.VideoCapture(str(CORPUS/(clip+'.mp4')))
            try:
                for index in range(48):
                    ok,bgr=cap.read()
                    if not ok:raise ValueError('Short source')
                    frame=cv2.cvtColor(cv2.resize(bgr,(1280,720)),cv2.COLOR_BGR2RGB)
                    depths={}
                    for variant,engine in engines.items():
                        token=engine.infer_device(frame)
                        engine.stream.synchronize()
                        depths[variant]=token.tensor.cpu().numpy().copy()
                        engine.complete_device(token)
                    reference=depths['fp32']
                    current=depths['fp32-current']
                    close=np.allclose(reference,current,atol=.001,rtol=.001)
                    strict=strict and close
                    scale=float(np.percentile(reference,98)-np.percentile(reference,2))
                    rows.append(dict(clip=clip,frame=index,range=scale,
                                     control_max_abs=float(np.max(np.abs(current-reference))),control_passed=bool(close),
                                     candidates={v:dict(mean_abs=float(np.abs(depths[v]-reference).mean()),
                                                        max_abs=float(np.max(np.abs(depths[v]-reference))),
                                                        normalized_percent=float(np.abs(depths[v]-reference).mean())/max(scale,1e-6)*100)
                                                 for v in ('encoder','encoder-spatial')}))
            finally:cap.release()
        result=dict(control_strict_passed=bool(strict),frames=rows,
                    outliers=sorted(rows,key=lambda r:r['candidates']['encoder']['normalized_percent'],reverse=True)[:4])
        args.output.write_text(json.dumps(result,indent=2))
        print(json.dumps(dict(control_strict_passed=bool(strict),outliers=result['outliers'])),flush=True)
    finally:
        for engine in engines.values():engine.close()


if __name__=='__main__':main()
