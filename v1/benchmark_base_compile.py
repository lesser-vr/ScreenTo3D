"""Fixed-input FP32 Base model-only comparison; no app backend changes."""
import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import statistics
import time

import cv2
import torch

from da2_base_experiment import Da2BaseOracle, WEIGHT_SHA256
from screento3d_app.da2_base import binding, preprocess
from screento3d_app.desktop_jobs import ROOT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    cache = ROOT/'out/base-compile-cache-20261105'
    os.environ['TORCHINDUCTOR_CACHE_DIR'] = str(cache/'inductor')
    os.environ['TRITON_CACHE_DIR'] = str(cache/'triton')
    os.environ['TORCHINDUCTOR_COMPILE_THREADS'] = '1'
    torch.set_num_threads(4)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch._dynamo.config.suppress_errors = False
    from torch._dynamo.utils import counters
    from torch._inductor import metrics
    import triton
    report = dict(completed=False,torch=torch.__version__,triton=triton.__version__,
        weight_sha256=WEIGHT_SHA256,shape=[1,3,518,924],precision='PyTorch FP32, AMP off, TF32 off; existing trusted TensorRT FP32 plan unchanged',
        scope='Same GPU input, model output only. No preprocess, source-depth upscale, stereo, capture or output FPS.',comparisons=[])
    try:
        with ExitStack() as stack, torch.inference_mode():
            runtime = Path('C:/TensorRT/TensorRT-11.2.1.2/bin')
            stack.enter_context(os.add_dll_directory(str(runtime)))
            backend = binding(ROOT/'out/da2-base-local',runtime)
            backend.input_validator(dict(width=1920,height=1080))
            engine = stack.enter_context(backend.engine_factory(None))
            oracle = stack.enter_context(Da2BaseOracle())
            compiled = torch.compile(oracle.model,mode='default',dynamic=False)
            rgb = cv2.cvtColor(cv2.imread(str(ROOT/'out/iw3-render-comparison-calibrated-20261105/FloorballGame/source.png')),cv2.COLOR_BGR2RGB)
            tensor = torch.from_numpy(preprocess(rgb,(518,924))).cuda()[None]
            torch.cuda.synchronize()
            assert engine.context.set_tensor_address('image',tensor.data_ptr())
            assert engine.context.set_tensor_address('depth',engine.output.data_ptr())
            stream = engine.stream
            def trt_forward():
                if not engine.context.execute_async_v3(stream.cuda_stream):
                    raise RuntimeError('TensorRT execution failed')
                return engine.output
            methods = {'tensorrt':trt_forward,'torch_eager':lambda:oracle.model(tensor),
                       'torch_compiled':lambda:compiled(tensor)}
            with torch.cuda.stream(stream):
                before = time.perf_counter()
                value = compiled(tensor)
                stream.synchronize()
                report['compile_first_call_seconds'] = time.perf_counter()-before
                assert bool(torch.isfinite(value).all())
                for _ in range(5):
                    for fn in methods.values():
                        fn()
                stream.synchronize()
                gpu = {k:[] for k in methods}
                wall = {k:[] for k in methods}
                for i in range(30):
                    order = list(methods)
                    order = order[i%3:]+order[:i%3]
                    for key in order:
                        a,b = torch.cuda.Event(enable_timing=True),torch.cuda.Event(enable_timing=True)
                        began = time.perf_counter()
                        a.record(stream);methods[key]();b.record(stream);b.synchronize()
                        gpu[key].append(a.elapsed_time(b))
                        wall[key].append((time.perf_counter()-began)*1000)
                report['median_gpu_ms'] = {k:statistics.median(v) for k,v in gpu.items()}
                report['median_host_ms'] = {k:statistics.median(v) for k,v in wall.items()}
                report['gpu_samples'] = gpu
                for case in ('FloorballGame','OfficeWalk','ParkingGarage'):
                    rgb = cv2.cvtColor(cv2.imread(str(ROOT/f'out/iw3-render-comparison-calibrated-20261105/{case}/source.png')),cv2.COLOR_BGR2RGB)
                    fresh = torch.from_numpy(preprocess(rgb,(518,924))).to(tensor.device)[None]
                    tensor.copy_(fresh)
                    reference = trt_forward().clone()
                    eager = oracle.model(tensor)
                    candidate = compiled(tensor)
                    assert all(bool(torch.isfinite(v).all()) for v in (reference,eager,candidate))
                    for left,right,a,b in [('trt','compiled',reference,candidate),('eager','compiled',eager,candidate)]:
                        error = (a-b).abs()
                        report['comparisons'].append(dict(case=case,reference=left,candidate=right,
                            mae=float(error.mean()),max=float(error.max()),reference_range=[float(a.min()),float(a.max())]))
            report['plan_sha256'] = engine.telemetry()['plan_sha256']
            report['completed'] = True
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        report['compiler_counters'] = {str(k):dict(v) for k,v in counters.items()}
        report['generated_kernel_count'] = metrics.generated_kernel_count
        (args.output/'report.json').write_text(json.dumps(report,indent=2,default=str),encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k not in ('compiler_counters','gpu_samples')},indent=2),flush=True)


if __name__=='__main__':
    main()
