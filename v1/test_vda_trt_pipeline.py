"""Real TensorRT pipeline lifecycle checks using the local fixed-shape binding."""
import argparse
import json
from pathlib import Path
import subprocess
import uuid
from unittest.mock import patch
import cv2
import numpy as np
from screento3d_app import pipeline
from vda_trt_experiment import ROOT,TensorRTVdaEngine,binding


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--input',type=Path,required=True)
    args=parser.parse_args()
    root=ROOT/'out/vda-trt-pipeline'/uuid.uuid4().hex; root.mkdir(parents=True)
    report=dict(passed=False,jobs=[])
    try:
        cap=cv2.VideoCapture(str(args.input))
        try:
            ok,bgr=cap.read()
            if not ok: raise RuntimeError('Unreadable source')
            frame=cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB)
        finally: cap.release()
        with TensorRTVdaEngine() as engine:
            first=engine.infer(frame)
            engine.infer(frame)
            engine.reset('scene_cut')
            np.testing.assert_array_equal(engine.infer(frame),first)
        assert engine.closed and not engine.history and not engine.engines
        report['reset_exact']=True
        assets=ROOT/'out/gpu-preview/ScreenTo3D-GPU-Preview/_internal'
        with patch('screento3d_app.resources.bundle_root',return_value=assets):
            metadata=pipeline.probe_video(args.input)
            for kind in ('cancel','failure','success'):
                job=root/kind; job.mkdir()
                output=job/'output.mp4'; output.write_bytes(b'prior-output')
                cancel=job/'cancel.flag'; engines=[]; processes=[]
                def factory(progress):
                    current=TensorRTVdaEngine(progress); engines.append(current)
                    if kind=='failure':
                        execute=current._execute
                        def fail(image):
                            if current.calls==1: raise RuntimeError('injected inference failure')
                            return execute(image)
                        current._execute=fail
                    return current
                def progress(event):
                    if kind=='cancel' and event['event']=='progress': cancel.touch()
                original=subprocess.Popen
                def track(*a,**kw):
                    process=original(*a,**kw); processes.append(process); return process
                result=None
                try:
                    with patch('subprocess.Popen',side_effect=track):
                        result=pipeline.convert_video(args.input,output,'video-quality',progress,cancel,
                            depth_backend=binding(factory),diagnostic_hashes=True)
                except InterruptedError: assert kind=='cancel'
                except RuntimeError as error: assert kind=='failure' and str(error)=='injected inference failure'
                else: assert kind=='success'
                assert len(engines)==1 and engines[0].closed and not engines[0].history and not engines[0].engines
                assert all(process.poll() is not None for process in processes)
                assert [p.name for p in job.iterdir()]==['output.mp4']
                if kind!='success': assert output.read_bytes()==b'prior-output'
                else:
                    cap=cv2.VideoCapture(str(output)); count=0
                    try:
                        while cap.read()[0]: count+=1
                    finally: cap.release()
                    assert count==result['frames']==metadata['total_frames']
                    # Probe only: wider validation envelope avoids treating an
                    # already-SBS output as a new H.264 conversion input.
                    outmeta=pipeline.probe_video(output,output_codec='hevc')
                    assert outmeta['width']==metadata['width']*2 and outmeta['height']==metadata['height']
                    assert outmeta['has_audio']==metadata['has_audio']
                    report['output_metadata']=outmeta
                report['jobs'].append(dict(kind=kind,passed=True,result=result))
                print('PASS: '+kind,flush=True)
            fixture=root/'cut-input.mp4'
            writer=cv2.VideoWriter(str(fixture),cv2.VideoWriter_fourcc(*'mp4v'),24,(frame.shape[1],frame.shape[0]))
            if not writer.isOpened(): raise RuntimeError('Fixture encoder unavailable')
            try:
                for index in range(48):
                    rgb=frame if index<24 else 255-frame
                    writer.write(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
            finally: writer.release()
            cut_result=pipeline.convert_video(fixture,root/'cut-output.mp4','video-quality',lambda event:None,
                depth_backend=binding())
            assert cut_result['frames']==48
            assert cut_result['telemetry']['scene_cut_resets']==1
            assert cut_result['telemetry']['resources']['resets']==2
            report['cut_result']=cut_result
            print('PASS: full-pipeline scene cut',flush=True)
        report['passed']=True
    finally:
        (root/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(root/'report.json',flush=True)


if __name__=='__main__': main()
