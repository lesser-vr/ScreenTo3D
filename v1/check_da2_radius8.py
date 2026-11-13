"""Compare pinned rolling and fixed radius-8 native paths on identical DA2 tokens."""
import argparse
from contextlib import ExitStack, nullcontext
from dataclasses import dataclass
import json
import os
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import torch

from compare_live_guide_radii import HFR, frames
from screento3d_app import live_gpu_texture
from screento3d_app.da2_base import binding
from screento3d_app.desktop_jobs import ROOT, BUNDLE
from screento3d_app.live_gpu_texture import LiveGpuTexture
from screento3d_app.live_policy import resolve_live
from screento3d_app.live_source_gpu_texture import LiveSourceGpuTexture
from screento3d_app.live_texture_pool import LiveTexturePool
from screento3d_app.resources import configure_resource_root
from screento3d_app.trt_backend import DepthEngine
from public_test_media import SOURCES


@dataclass(frozen=True)
class Build:
    directory: str
    base: str
    small: str
    pool: str


BUILDS = (
    Build('guide-common', '85261b5df16bfa22c30dcb768640b462eb16040cd36e9844247bc9705438663f',
          '3e56bde920f0b9007203c95f045dcb85a6fdf1aaa34a3c98964dd1b200b8519a',
          '9728e0a5d57f75a083af88abf538cb2ec0081ff276f71657a10cad65776e3555'),
    Build('guide-fixed8', 'c795770368894d92c9f38647bed741822d55e2dea9f20c3a09a8af845411056e',
          '54a26a5d64903ba3d47a6b0393a0d40a8a4f3b1a56b94fd7b6a7c8c29928a066',
          '64a022c442ead88b0f673bd9e7b8975fec6b4271182b605f380695d3418dcfc4'),
)


def renderer(stack, build, mode, engine, width, height):
    directory = ROOT/'out'/build.directory
    is_base = mode == 'balanced'
    parent = LiveSourceGpuTexture if is_base else LiveGpuTexture
    digest = build.base if is_base else build.small

    class Pool(LiveTexturePool):
        library_path = directory/'live_texture_runtime.dll'
        library_sha256 = build.pool

    class Native(parent):
        library_path = directory/('live_depth.dll' if is_base else 'small_input.dll')
        library_sha256 = borrowed_layout_sha256 = digest

    with patch.object(live_gpu_texture, 'LiveTexturePool', Pool):
        run = stack.enter_context(Native(width, height, resolve_live(mode, .5), engine, diagnostic=True))
    run.configure_live_quality('detail')
    run.slot = 0
    assert run.policy.depth_guide_radius == 8
    return run


def edge_frames(width, height):
    y, x = np.indices((height, width))
    for i in range(36):
        rgb = np.zeros((height, width, 3), np.uint8)
        rgb[:] = (15, 15, 15) if i < 18 else (118, 119, 120)
        rgb[(y > 5) & (y < height-9) & (((x+i) % 47) < 2)] += 24
        rgb[height//3:height*2//3, width//3+i:width//2+i] = (180, 165, 150)
        yield rgb


def compare(clip, mode, directory, runtime):
    if clip == 'thin-flat':
        w, h = 513, 289
        inputs = edge_frames(w, h)
    else:
        w, h = (3840,2160) if clip in HFR else (1920,1080)
        inputs = frames(clip, 36)
    rows = []
    with ExitStack() as stack:
        if mode == 'balanced':
            backend = binding(ROOT/'out/da2-base-local', runtime, device_depth=True)
            backend.input_validator(dict(width=w, height=h))
            engine = stack.enter_context(backend.engine_factory(None))
        else:
            engine = stack.enter_context(DepthEngine())
        runs = [renderer(stack, build, mode, engine, w, h) for build in BUILDS]
        timing_input = torch.empty((3,518,518),device='cuda')
        pad = np.zeros((518,518,3),np.uint8)
        for run in runs:
            run._check(run.dll.live_prepare(run.handle, pad.ctypes.data, timing_input.data_ptr()))
        for i, rgb in enumerate(inputs):
            if i == 18:
                for run in runs:
                    run.reset()
            token = runs[0].infer(rgb)
            outputs = {}
            row = dict(frame=i)
            order = (0,1) if i % 2 == 0 else (1,0)
            for index in order:
                run = runs[index]
                run.source_ns = 1_000_000_000 + round(i*1e9/60)
                # Keep the single token alive until both same-stream renders finish.
                completion = patch.object(engine,'complete_device',lambda t:t.validate()) if index == order[0] else nullcontext()
                with completion:
                    _, depth = run.render(rgb, token, diagnostic=True)
                times = np.empty(8,np.float32)
                run._check(run.dll.live_times(run.handle,times.ctypes.data))
                row[f'ms{index}'] = float(times[5])
                pixels = np.empty((h,w*2,4),np.uint8)
                run.pool.check(run.pool.dll.live_pool_readback(run.pool.handle,0,pixels.ctypes.data))
                outputs[index] = depth,pixels
            error = np.abs(outputs[0][0] - outputs[1][0])
            assert np.isfinite(error).all()
            row.update(depth_max=float(error.max()),depth_mae=float(error.mean()),
                       different_channels=int(np.count_nonzero(outputs[0][1] != outputs[1][1])))
            rows.append(row)
    summary = dict(clip=clip,mode=mode,size=[w,h],frames=len(rows),
                   guide_ms=[float(np.median([r[f'ms{k}'] for r in rows[6:]])) for k in (0,1)],
                   max_depth=max(r['depth_max'] for r in rows),max_mae=max(r['depth_mae'] for r in rows),
                   different_channels=sum(r['different_channels'] for r in rows))
    (directory/f'{clip}-{mode}.json').write_text(json.dumps(dict(summary=summary,rows=rows),indent=2))
    print(json.dumps(summary),flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    configure_resource_root(BUNDLE)
    cv2.setNumThreads(2)
    runtime = Path('C:/TensorRT/TensorRT-11.2.1.2/bin')
    with os.add_dll_directory(str(runtime)):
        results = [compare(name, mode, args.output, runtime)
                   for name in (*HFR,*SOURCES,'thin-flat') for mode in ('balanced','performance')]
    assert all(r['max_depth'] <= 1e-4 and r['max_mae'] <= 1e-6 and r['different_channels'] == 0 for r in results)


if __name__ == '__main__':
    main()
