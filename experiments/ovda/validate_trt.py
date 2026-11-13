# Personal non-commercial oVDA integration test, NC-SA-UHDV1.0.
import json
from pathlib import Path
import uuid
from unittest.mock import patch
import cv2
import numpy as np
import torch
from oracle import ROOT, OvdaOracle
from trt_engine import OvdaTrt


def main():
    from screento3d_app import pipeline
    from screento3d_app.resources import configure_media_tools
    from screento3d_app.depth_backend import BackendBinding, BackendSpec
    from evaluate_depth_models import inspect_media, sha
    from temporal_diagnostics import TemporalProbe
    from vda_comparison import BoundedEngine, validate_runs, inspection_sheet
    configure_media_tools(ROOT/'out/gpu-preview/ScreenTo3D-GPU-Preview/_internal/ffmpeg')
    torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    root=ROOT/'out/ovda-trt-integration'/uuid.uuid4().hex;root.mkdir(parents=True)
    live=ROOT/'out/live-action-evaluation/eab25eb5c4b948b2a11b5ce3dad79a2f'
    folders=[live/n for n in ('OfficeWalk','HighwayDrive','FloorballGame','ParkingGarage','KnownCut')]
    folders.append(ROOT/'out/live-action-supplement/475182585c664d51977a3a68ad421951')
    report=dict(passed=False,comparisons=[],clips=[],note='Diagnostics only, no performance rank or default promotion')
    print(root,flush=True)
    try:
        capture=cv2.VideoCapture(str(live/'FloorballGame/input.mp4'))
        try:
            with OvdaOracle() as reference,OvdaTrt() as candidate:
                for index in range(32):
                    ok,bgr=capture.read();assert ok
                    frame=cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB)
                    a,b=reference.infer(frame),candidate.infer(frame)
                    np.testing.assert_allclose(a,b,atol=.001,rtol=.001)
                    report['comparisons'].append(float(np.max(np.abs(a-b))))
                    if index==0:first=frame.copy();golden=b.copy()
                for reason in ('scene_cut','source_change','discontinuity'):
                    candidate.reset(reason)
                    np.testing.assert_allclose(candidate.infer(first),golden,atol=0,rtol=0)
                report['engine']=candidate.telemetry()
            candidate.close()
            try:candidate.infer(first)
            except RuntimeError:pass
            else:raise AssertionError('Closed engine accepted')
        finally:capture.release()
        binding=BackendBinding(BackendSpec('ovda-small-c16','tensorrt-fp32-experiment',True,True),
            lambda p:BoundedEngine(OvdaTrt(p),124),lambda f:f)
        original=pipeline.StereoSynthesizer.render
        for source_folder in folders:
            name=source_folder.name if source_folder.parent==live else 'Beauty'
            folder=root/name;folder.mkdir();input_path=source_folder/'input.mp4';output=folder/'ovda.mp4'
            meta=pipeline.probe_video(input_path);probe=TemporalProbe();parity=[]
            def render(renderer,frame,depth):
                cut=renderer.is_scene_cut(frame);probe.add(frame,depth,cut=cut)
                result=original(renderer,frame,depth)
                if cut:
                    fresh=pipeline.StereoSynthesizer(renderer.width,renderer.height,renderer.policy)
                    maximum=int(np.abs(result.astype(np.int16)-original(fresh,frame,depth).astype(np.int16)).max())
                    assert maximum==0;parity.append(dict(frame=len(probe.rows)-1,max_abs=maximum))
                return result
            with patch.object(pipeline.StereoSynthesizer,'render',render):
                result=pipeline.convert_video(input_path,output,'video-quality',lambda e:None,
                    depth_backend=binding,diagnostic_hashes=True)
            inspect_media(output,meta)
            matched={m:json.loads((source_folder/f'{m}.json').read_text()) for m in ('small','base','vda')}
            validate_runs({**matched,'ovda':result},120,120)
            item=dict(name=name,input_sha256=sha(input_path),result=result,
                temporal=probe.report(),cut_parity=parity,
                reference_temporal={m:r['motion_compensated_depth']['summary'] for m,r in matched.items()})
            if name=='KnownCut':assert [r['frame'] for r in parity]==[60]
            report['clips'].append(item)
            captures=[cv2.VideoCapture(str(p)) for p in (input_path,source_folder/'vda.mp4',output)]
            try:
                images=[]
                for cap in captures:
                    cap.set(cv2.CAP_PROP_POS_FRAMES,60);ok,frame=cap.read();assert ok;images.append(frame)
                rows=[('SOURCE duplicated',np.concatenate([images[0],images[0]],axis=1)),
                    ('VDA left / right',images[1]),('oVDA c16 left / right',images[2])]
                cv2.imwrite(str(folder/'comparison-60.jpg'),inspection_sheet(rows,1280,720))
            finally:
                for cap in captures:cap.release()
            print('PASS '+name+' matched conversion',flush=True)
        report['passed']=True
    finally:
        (root/'report.json').write_text(json.dumps(report,indent=2))
        print(root/'report.json',flush=True)


if __name__=='__main__':main()
