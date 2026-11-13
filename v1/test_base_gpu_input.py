"""Real CUDA preprocessing comparison; no capture or model inference required."""
import argparse
import json
import time
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import torch

from screento3d_app.base_gpu_input import BaseGpuInput
from screento3d_app.da2_base import preprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    cv2.setNumThreads(1)
    torch.set_num_threads(1)
    stream = torch.cuda.Stream()
    engine = SimpleNamespace(_check=lambda: None, device=0, torch=torch, stream=stream, shape=(518, 924))
    prepare = BaseGpuInput(engine)
    rng = np.random.default_rng(721)
    report = dict(passed=False, cases=[], scope='CUDA preprocessing vs original OpenCV float64; no FPS claim')
    try:
        for width, height in ((16,16),(17,21),(32,32),(64,64),(65,63),(924,518),(1920,1080),(3440,1440),(1080,1920),(3840,2160),(4096,2160)):
            for pattern in ('random','gradient','flat'):
                rgb = rng.integers(0, 256, (height,width,3), dtype=np.uint8)
                if pattern == 'gradient':
                    rgb[:] = np.linspace(0,255,width,dtype=np.uint8)[None,:,None]
                elif pattern == 'flat':
                    rgb[:] = (19,128,242)
                for shape in ((518,896),(518,924)):
                    engine.shape = shape
                    began = time.perf_counter()
                    expected = preprocess(rgb, shape)
                    cpu_ms = (time.perf_counter()-began)*1000
                    with torch.cuda.stream(stream):
                        device = torch.from_numpy(rgb).cuda()
                        actual = prepare.prepare(device)[0].cpu().numpy()
                    stream.synchronize()
                    delta = np.abs(actual-expected)
                    row = dict(size=[width,height],shape=shape,pattern=pattern,
                        exact=bool(np.array_equal(actual,expected)),max=float(delta.max()),mae=float(delta.mean()),cpu_ms=cpu_ms)
                    report['cases'].append(row)
                    print(json.dumps(row),flush=True)
                    assert row['exact']
                    thumb = prepare.thumbnail(device)
                    assert np.array_equal(thumb, cv2.resize(rgb, (32,32))), ('thumbnail', width, height, np.max(np.abs(thumb.astype(int)-cv2.resize(rgb,(32,32)).astype(int))))
                    bgra = np.empty((height,width+8,4), np.uint8)
                    bgra[:,:width,:3] = rgb[:,:,::-1]
                    with torch.cuda.stream(stream):
                        pitched = torch.from_numpy(bgra).cuda()[:,:width]
                        actual_bgra = prepare.prepare(pitched)[0].cpu().numpy()
                    assert np.array_equal(actual_bgra, expected)
                    row.update(thumbnail_exact=True, pitched_bgra_exact=True)
        try:
            prepare.prepare(device)
        except RuntimeError:
            pass
        else:
            raise AssertionError('Foreign stream context accepted')
        with torch.cuda.stream(stream):
            for invalid in (torch.zeros((16,16,3), dtype=torch.uint8),
                    torch.zeros((16,16,3), device='cuda', dtype=torch.float32),
                    torch.zeros((16,16,2), device='cuda', dtype=torch.uint8),
                    torch.zeros((16,16,3), device='cuda', dtype=torch.uint8).transpose(0,1)):
                try:
                    prepare.prepare(invalid)
                except ValueError:
                    pass
                else:
                    raise AssertionError('Invalid input accepted')
        report['input_rejection_checks'] = 5
        report['passed'] = True
    finally:
        (args.output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')


if __name__ == '__main__':
    main()
