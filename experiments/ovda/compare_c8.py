# NC-SA-UHDV1.0; optional c8 quality gate, never an application registration.
import argparse
import json
from pathlib import Path
import uuid
from unittest.mock import patch
import cv2
import numpy as np
import torch
from oracle import ROOT, OvdaOracle
from depthsbs_app import pipeline
from depthsbs_app.depth_backend import BackendBinding, BackendSpec
from depthsbs_app.resources import configure_media_tools
from temporal_diagnostics import TemporalProbe
from evaluate_depth_models import inspect_media, sha


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--original',type=Path,required=True)
    args=parser.parse_args()
    root=ROOT/'out/ovda-c8-quality'/uuid.uuid4().hex;root.mkdir(parents=True)
    print(root,flush=True)
    configure_media_tools(ROOT/'out/gpu-preview/DepthSBS-GPU-Preview/_internal/ffmpeg')
    torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    report=dict(passed=False,clips=[],note='c8 PyTorch quality candidate, not TRT or speed comparison')
    cap=cv2.VideoCapture(str(args.original)); frames=[]
    try:
        for _ in range(32):
            ok,bgr=cap.read();assert ok
            frames.append(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB))
    finally:cap.release()
    try:
        with OvdaOracle(cache_size=8) as oracle:
            batch=oracle.model.infer_video_depth(np.stack(frames),device='cuda',preprocess_device='cpu',fp32=True)[0]
            maxima=[]
            for frame,expected in zip(frames,batch):
                actual=oracle.infer(frame)[0]
                np.testing.assert_allclose(actual,expected,atol=.001,rtol=.001)
                maxima.append(float(np.abs(actual-expected).max()))
            report['original_batch_parity_maxima']=maxima
            oracle.reset('scene_cut')
            np.testing.assert_allclose(oracle.infer(frames[0])[0],batch[0],atol=.001,rtol=.001)
        for name,source in (
            ('avatar',args.original),
            ('FloorballGame',ROOT/'out/live-action-evaluation/eab25eb5c4b948b2a11b5ce3dad79a2f/FloorballGame/input.mp4'),
            ('Beauty',ROOT/'out/live-action-supplement/475182585c664d51977a3a68ad421951/input.mp4')):
            probe=TemporalProbe(); original=pipeline.StereoSynthesizer.render
            def render(renderer,frame,depth):
                probe.add(frame,depth,cut=renderer.is_scene_cut(frame))
                return original(renderer,frame,depth)
            binding=BackendBinding(BackendSpec('ovda-small-c8','pytorch-cuda-fp32-experiment',True,True),
                                   lambda p:OvdaOracle(p,cache_size=8),lambda f:f)
            output=root/f'{name}.mp4'
            with patch.object(pipeline.StereoSynthesizer,'render',render):
                result=pipeline.convert_video(source,output,'video-quality',lambda e:None,depth_backend=binding,diagnostic_hashes=True)
            inspect_media(output,pipeline.probe_video(source))
            report['clips'].append(dict(name=name,input_sha256=sha(source),result=result,temporal=probe.report()))
            print('PASS c8 quality capture',name,flush=True)
        report['passed']=True
    finally:
        (root/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(root/'report.json',flush=True)


if __name__=='__main__':main()
