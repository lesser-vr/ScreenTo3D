# oVDA aspect validation, NC-SA-UHDV1.0; see LICENSE/README.md.
"""Actual installed engine host/device restoration parity and canvas selection."""
import argparse
import json
from pathlib import Path
import cv2
import numpy as np
from depthsbs_app import ovda
from depthsbs_app.desktop_jobs import ROOT
from public_test_media import CORPUS


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    host_class=ovda.runtime_class(False);device_class=ovda.runtime_class(True)
    profiles=ovda.profiles(ROOT/'out/ovda-local')
    cap=cv2.VideoCapture(str(CORPUS/'FloorballGame.mp4'))
    originals=[]
    try:
        for _ in range(3):
            ok,frame=cap.read()
            if not ok:raise ValueError('Short public source')
            originals.append(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
    finally:cap.release()
    rows=[]
    for w,h in ((3440,1440),(1080,1920),(1024,1024),(1056,608),(1280,720),(960,720),(1920,1080),(3840,2160)):
        shape=ovda.input_shape(dict(width=w,height=h),profiles)
        kwargs=dict(directory=profiles[shape],profile=shape)
        host=host_class(**kwargs);device=device_class(**kwargs)
        errors=[]
        try:
            for original in originals:
                frame=np.ascontiguousarray(cv2.resize(original,(w,h)))
                expected=host.infer(frame)
                token=device.infer_device(frame)
                device.stream.synchronize()
                actual=token.tensor.cpu().numpy().copy()
                device.complete_device(token)
                assert actual.shape==expected.shape==(1,h,w)
                error=float(np.abs(actual-expected).max())
                errors.append(error)
                np.testing.assert_array_equal(actual,expected)
            rows.append(dict(size=[w,h],canvas=shape,frames=3,max_abs=max(errors),host_device_exact=True))
            print('PASS',w,h,shape,flush=True)
        finally:host.close();device.close()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(dict(passed=True,cases=rows),indent=2))


if __name__=='__main__':main()
