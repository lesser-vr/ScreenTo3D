"""Bounded model-only precision feasibility probe; no product artifact changes."""
import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import statistics

import numpy as np
import torch

from da2_base_experiment import Da2BaseOracle, WEIGHT_SHA256
from depthsbs_app.da2_base import binding, preprocess
from depthsbs_app.desktop_jobs import ROOT
from public_test_media import PublicFrames
from base_trt_fp16_trial import installed


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    torch.set_num_threads(4)
    torch.backends.cuda.matmul.allow_tf32=False
    torch.backends.cudnn.allow_tf32=False
    report=dict(completed=False,torch=torch.__version__,gpu=torch.cuda.get_device_name(),
        weight_sha256=WEIGHT_SHA256,shape=[1,3,518,924],bf16_supported=torch.cuda.is_bf16_supported(),
        scope='TensorRT FP32 control versus original PyTorch FP32 and autocast FP16/BF16; model-only, no compiled half plan, quantization, SBS or perceptual acceptance',cases=[])
    try:
        with ExitStack() as stack,torch.inference_mode():
            runtime=Path('C:/TensorRT/TensorRT-11.2.1.2/bin')
            stack.enter_context(os.add_dll_directory(str(runtime)))
            with installed('fp32'):
                backend=binding(ROOT/'out/da2-base-local',runtime)
                backend.input_validator(dict(width=1920,height=1080))
                engine=stack.enter_context(backend.engine_factory(None))
            oracle=stack.enter_context(Da2BaseOracle())
            report['plan_sha256']=engine.telemetry()['plan_sha256']
            with torch.cuda.stream(engine.stream):
                tensor=torch.zeros((1,3,518,924),device='cuda')
                assert engine.context.set_tensor_address('image',tensor.data_ptr())
                assert engine.context.set_tensor_address('depth',engine.output.data_ptr())
                def trt():
                    if not engine.context.execute_async_v3(engine.stream.cuda_stream):raise RuntimeError('TRT failed')
                    return engine.output
                def amp(dtype):
                    with torch.autocast('cuda',dtype=dtype):return oracle.model(tensor).float()
                methods={'trt_fp32':trt,'torch_fp32':lambda:oracle.model(tensor),
                         'torch_amp_fp16':lambda:amp(torch.float16),'torch_amp_bf16':lambda:amp(torch.bfloat16)}
                first=next(iter(PublicFrames('FloorballGame',1)))
                tensor.copy_(torch.from_numpy(preprocess(first,(518,924)))[None].to('cuda'))
                for _ in range(5):
                    for method in methods.values():method()
                engine.stream.synchronize()
                times={key:[] for key in methods}
                for repeat in range(30):
                    keys=list(methods);keys=keys[repeat%4:]+keys[:repeat%4]
                    for key in keys:
                        a,b=torch.cuda.Event(enable_timing=True),torch.cuda.Event(enable_timing=True)
                        a.record(engine.stream);methods[key]();b.record(engine.stream);b.synchronize()
                        times[key].append(a.elapsed_time(b))
                report['median_model_gpu_ms']={key:statistics.median(values) for key,values in times.items()}
                report['timing_samples']=times
                def compare(rgb,label):
                    tensor.copy_(torch.from_numpy(preprocess(rgb,(518,924)))[None].to('cuda'))
                    baseline=oracle.model(tensor).float()
                    for name in ('trt_fp32','torch_amp_fp16','torch_amp_bf16'):
                        value=methods[name]().float()
                        finite=bool(torch.isfinite(value).all())
                        row=dict(case=label,candidate=name,finite=finite)
                        if finite:
                            error=(baseline-value).abs()
                            low,high=torch.quantile(baseline.flatten(),torch.tensor([.02,.98],device='cuda'))
                            scale=(high-low).clamp_min(1e-6)
                            row.update(raw_mae=float(error.mean()),raw_max=float(error.max()),
                                error_over_reference_p2_p98=float(error.mean()/scale),
                                historical_raw_allclose=bool(torch.allclose(baseline,value,atol=.001,rtol=.001)))
                        report['cases'].append(row)
                for name in ('FloorballGame','OfficeWalk','ParkingGarage'):
                    for index,rgb in enumerate(PublicFrames(name,36)):
                        if index%3==0:compare(rgb,f'{name}-{index}')
                for level in (0,127,255):compare(np.full((1080,1920,3),level,np.uint8),f'constant-{level}')
                engine.stream.synchronize()
            report['completed']=True
    finally:
        (args.output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k not in ('timing_samples','cases')}),flush=True)


if __name__=='__main__':main()
