"""Matched eager/torch.compile renderer probe; does not change app defaults."""
import argparse
import json
import os
from pathlib import Path
import statistics
import time

import cv2
import numpy as np
import torch

from compare_iw3_renderers import models, synthetic, save_rgb, REVISION, WEIGHTS
from depthsbs_app.desktop_jobs import ROOT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--static', action='store_true', help='Compile separately for each fixed source size')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    cache = ROOT / 'out/iw3-compile-cache-20261105'
    os.environ['TORCHINDUCTOR_CACHE_DIR'] = str(cache / 'inductor')
    os.environ['TRITON_CACHE_DIR'] = str(cache / 'triton')
    os.environ['TORCHINDUCTOR_COMPILE_THREADS'] = '1'
    torch.set_num_threads(4)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch._dynamo.config.suppress_errors = False
    loaded = models(ROOT/'out/iw3-render-source-20261105', ROOT/'out/iw3-render-models-20261105')
    from iw3.backward_warp import apply_divergence_nn_LR
    from torch._dynamo.utils import counters
    from torch._inductor import metrics
    import triton
    report = dict(passed=False, torch=torch.__version__, triton=triton.__version__,
                  revision=REVISION, weights=WEIGHTS, mode='default',
                  dynamic=False if args.static else None,
                  compile_scope='model only, matching iw3 --compile; fullgraph=False; no suppressed errors',
                  timing_scope='GPU-resident complete paired renderer, excludes input transfer and RGB readback; not app FPS',
                  precision='same upstream AMP FP16, RGB/depth FP32, TF32 off', rows=[])
    source = ROOT/'out/iw3-render-comparison-calibrated-20261105'
    cases = []
    for name in ('FloorballGame', 'OfficeWalk', 'ParkingGarage'):
        rgb = cv2.cvtColor(cv2.imread(str(source/name/'source.png')), cv2.COLOR_BGR2RGB)
        depth = np.load(source/name/'depth.npy', allow_pickle=False)
        cases.append((name, rgb, depth))
    rgb, depth, _, _ = synthetic()
    cases.append(('synthetic', cv2.resize(rgb,(1920,1080)), cv2.resize(depth,(1920,1080))))
    cases.append(('OfficeWalk4K', cv2.resize(cases[1][1],(3840,2160)), cv2.resize(cases[1][2],(3840,2160))))

    def render(model, color, depth):
        left, right = apply_divergence_nn_LR(model,color,depth,2.6,.45,steps=1,enable_amp=True)
        return left, right

    def pixels(eyes):
        assert all(bool(torch.isfinite(eye).all()) for eye in eyes), 'Nonfinite renderer output'
        return torch.cat(eyes,3).clamp(0,1).mul(255).round().to(torch.uint8)[0].permute(1,2,0).cpu().numpy()

    try:
        for name, eager in loaded.items():
            compiled = torch.compile(eager, mode='default', dynamic=False if args.static else None)
            for case, rgb, depth in cases:
                c = torch.from_numpy(rgb).cuda().permute(2,0,1)[None].float().div(255)
                d = torch.from_numpy(np.ascontiguousarray(depth)).cuda()[None,None]
                with torch.inference_mode():
                    reference = pixels(render(eager,c,d))
                    torch.cuda.synchronize()
                    before_kernels = metrics.generated_kernel_count
                    began = time.perf_counter()
                    result = pixels(render(compiled,c,d))
                    first_seconds = time.perf_counter()-began
                    error = np.abs(reference.astype(np.int16)-result.astype(np.int16))
                    row = dict(method=name,case=case,size=[rgb.shape[1],rgb.shape[0]],
                               first_call_seconds=first_seconds,
                               new_generated_kernels=metrics.generated_kernel_count-before_kernels,
                               rgb_mae=float(error.mean()),rgb_max=int(error.max()),
                               changed_fraction=float(np.mean(np.any(error!=0,2))))
                    if case in ('FloorballGame','OfficeWalk4K'):
                        for _ in range(5):
                            render(eager,c,d); render(compiled,c,d)
                        torch.cuda.synchronize()
                        times = {'eager':[], 'compiled':[]}
                        wall = {'eager':[], 'compiled':[]}
                        for i in range(30):
                            pairs = [('eager',eager),('compiled',compiled)]
                            if i%2:
                                pairs.reverse()
                            for key,model in pairs:
                                a,b = torch.cuda.Event(enable_timing=True),torch.cuda.Event(enable_timing=True)
                                start = time.perf_counter()
                                a.record()
                                render(model,c,d)
                                b.record();b.synchronize()
                                wall[key].append((time.perf_counter()-start)*1000)
                                times[key].append(a.elapsed_time(b))
                        row['gpu_ms'] = {k:statistics.median(v) for k,v in times.items()}
                        row['host_elapsed_ms'] = {k:statistics.median(v) for k,v in wall.items()}
                        row['gpu_samples'] = times
                        row['speedup'] = row['gpu_ms']['eager']/row['gpu_ms']['compiled']
                    # Save one reproducible visual pair per model at 1080p.
                    if case=='OfficeWalk':
                        save_rgb(args.output/(name+'-eager.png'),reference)
                        save_rgb(args.output/(name+'-compiled.png'),result)
                    report['rows'].append(row)
                    print(json.dumps({k:v for k,v in row.items() if k!='gpu_samples'}),flush=True)
                del c,d
        report['passed'] = True
    except Exception as error:
        report['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        report['dynamo_counters'] = {str(k):dict(v) for k,v in counters.items()}
        report['generated_kernel_count'] = metrics.generated_kernel_count
        (args.output/'report.json').write_text(json.dumps(report,indent=2,default=str),encoding='utf-8')


if __name__=='__main__':
    main()
