# NC-SA-UHDV1.0; see accompanying LICENSE and attribution.
"""Real short-job cancellation/failure preservation for optional CUDA experiment."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import uuid
import torch
from oracle import OvdaOracle, ROOT


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--backend', choices=('pytorch','tensorrt'), default='pytorch')
    args=parser.parse_args()
    if args.backend=='tensorrt':
        from trt_engine import OvdaTrt
        engine_class=OvdaTrt
    else:
        engine_class=OvdaOracle
    from depthsbs_app import pipeline
    from depthsbs_app.depth_backend import BackendSpec, BackendBinding
    from depthsbs_app.resources import configure_media_tools
    configure_media_tools(ROOT/'out/gpu-preview/DepthSBS-GPU-Preview/_internal/ffmpeg')
    torch.backends.cuda.matmul.allow_tf32=False
    torch.backends.cudnn.allow_tf32=False
    root=ROOT/'out/ovda-failures'/uuid.uuid4().hex;root.mkdir(parents=True)
    report=dict(passed=False,cases=[])
    print(root,flush=True)
    try:
        for failure in (False,True):
            owned=[]
            def factory(progress):
                engine=engine_class(progress);owned.append(engine)
                if failure:
                    original=engine.infer
                    def infer(frame):
                        if engine.calls==3: raise RuntimeError('injected oVDA failure')
                        return original(frame)
                    engine.infer=infer
                return engine
            binding=BackendBinding(BackendSpec('ovda-small-c16','pytorch-cuda-fp32-experiment',True,True),factory,lambda f:f)
            output=root/('failure.mp4' if failure else 'cancel.mp4')
            sentinel=b'preserve existing user output';output.write_bytes(sentinel)
            cancel=root/'cancel.flag'
            def progress(event):
                if not failure and event.get('event')=='progress' and event['frame']>=1:cancel.touch()
            try:
                pipeline.convert_video(args.input,output,'video-quality',progress,
                    None if failure else cancel,depth_backend=binding)
            except (InterruptedError,RuntimeError) as error:
                if failure and 'injected oVDA failure' not in str(error):raise
                if not failure and not isinstance(error,InterruptedError):raise
            else:raise AssertionError('Expected abort')
            assert output.read_bytes()==sentinel
            assert len(owned)==1 and owned[0].closed and not owned[0].cache
            assert getattr(owned[0],'model',None) is None and getattr(owned[0],'context',None) is None
            report['cases'].append(dict(case='failure' if failure else 'cancel',passed=True,
                                        completed_inferences=owned[0].calls))
        report['passed']=True
    finally:
        (root/'report.json').write_text(json.dumps(report,indent=2))
        print(root/'report.json',flush=True)


if __name__=='__main__':main()
