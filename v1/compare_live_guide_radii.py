"""Paired DA2 radius comparison on public frames, without desktop capture."""
import argparse
import ctypes as ct
from contextlib import ExitStack, contextmanager, nullcontext
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
from unittest.mock import patch

import cv2
import numpy as np
import torch

from screento3d_app.da2_base import binding
from screento3d_app.desktop_jobs import BUNDLE, ROOT
from screento3d_app.live_gpu_texture import LiveGpuTexture
from screento3d_app.live_source_gpu_texture import LiveSourceGpuTexture
from screento3d_app.live_policy import resolve_live
from screento3d_app.resources import configure_resource_root
from screento3d_app.trt_backend import DepthEngine
from public_test_media import PublicFrames, SOURCES

HFR = {
    'Jockey': '36609adcf8d36db4c842003ebfa661fc03f9ad4bb750bd889ea52aab6651831c',
    'Beauty': 'ad705b937081ad4e62faa68a30c4d30a06a18b81410996b24b01a4fd9119b39c',
}
RADII = (4, 8)


def frames(name, count):
    if name in SOURCES:
        yield from PublicFrames(name, count)
        return
    path = ROOT / 'out/public-hfr' / f'{name}-120.mp4'
    if hashlib.sha256(path.read_bytes()).hexdigest() != HFR[name]:
        raise ValueError('Public source checksum mismatch')
    cap = cv2.VideoCapture(str(path))
    try:
        assert cap.set(cv2.CAP_PROP_POS_FRAMES, 120)
        for _ in range(count):
            ok, bgr = cap.read()
            assert ok and cap.grab()  # Select every other 120 Hz frame for 60 Hz input.
            yield cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    finally:
        cap.release()


@contextmanager
def review_encoder(path, w, h):
    cmd = [str(BUNDLE / 'ffmpeg/ffmpeg.exe'), '-loglevel', 'error', '-n',
           '-f', 'rawvideo', '-pixel_format', 'rgba', '-video_size', f'{w*2}x{h}',
           '-framerate', '60', '-i', 'pipe:0', '-an', '-c:v', 'hevc_nvenc',
           '-preset', 'p4', '-rc', 'constqp', '-qp', '15', '-pix_fmt', 'yuv420p',
           '-metadata', 'comment=UVG Jockey, Ultra Video Group, Tampere University. CC BY-NC 3.0. Modified to Full SBS.',
           str(path)]
    with subprocess.Popen(cmd, stdin=subprocess.PIPE) as process:
        try:
            yield process.stdin
        finally:
            process.stdin.close()
        if process.wait():
            raise RuntimeError(f'Failed to encode {path.name}')


def run_case(name, mode, count, out, runtime, review=False, *, builds=None, source=None):
    w, h = (3840, 2160) if name in HFR else (1920, 1080)
    variants = tuple(builds) if builds else RADII
    inputs = frames(name, count)
    if source is not None:
        (w, h), inputs = source
    reduced = (w // 4, h // 4)
    xx, yy = np.meshgrid(np.arange(reduced[0], dtype=np.float32),
                         np.arange(reduced[1], dtype=np.float32))
    flow = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_FAST)
    previous = prior_gray = None
    rows = []
    with ExitStack() as stack:
        if mode == 'balanced':
            backend = binding(ROOT / 'out/da2-base-local', runtime, device_depth=True)
            backend.input_validator(dict(width=w, height=h))
            engine = stack.enter_context(backend.engine_factory(None))
            renderer = LiveSourceGpuTexture
        else:
            engine = stack.enter_context(DepthEngine())
            renderer = LiveGpuTexture
        runs = {}
        movies = {}
        tensor = torch.empty((3, 518, 518), device='cuda')
        padding = np.zeros((518, 518, 3), np.uint8)
        for variant in variants:
            if builds:
                run = builds[variant](stack, mode, engine, w, h)
            else:
                policy = replace(resolve_live(mode, .5), depth_guide_radius=variant)
                run = stack.enter_context(renderer(w, h, policy, engine, diagnostic=True))
                run.configure_live_quality('detail')
                run.slot = 0
            run.dll.live_shift_snapshot.argtypes = [ct.c_void_p, ct.c_void_p]
            # Initialize the first two events required by live_times; use only events 5–6.
            run._check(run.dll.live_prepare(run.handle, padding.ctypes.data, tensor.data_ptr()))
            runs[variant] = run
            if review:
                label = variant if builds else f'r{variant}'
                movies[variant] = stack.enter_context(review_encoder(out / f'{name}-{mode}-{label}-FullSBS.mp4', w, h))
        for i, rgb in enumerate(inputs):
            token = runs[variants[0]].infer(rgb)
            gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
            edge = cv2.dilate(cv2.Canny(gray, 40, 100), np.ones((3, 3), np.uint8)) > 0
            gray = cv2.resize(gray, reduced, interpolation=cv2.INTER_AREA)
            shifts, eyes = {}, {}
            row = dict(frame=i)
            order = variants if i % 2 == 0 else variants[::-1]
            for variant in order:
                run = runs[variant]
                run.source_ns = 1_000_000_000 + round(i * 1e9 / 60)
                scene = run.inspect_scene(rgb)
                row['cut'] = bool(scene.cut)
                # The first synchronized consumer borrows the pending token;
                # the second releases it on the same owner stream.
                completion = patch.object(engine, 'complete_device', lambda depth: depth.validate()) if variant == order[0] else nullcontext()
                with completion:
                    run.render(rgb, token, scene=scene)
                times = np.empty(8, np.float32)
                run._check(run.dll.live_times(run.handle, times.ctypes.data))
                row[f'ms{variant}'] = float(times[5])
                shift = np.empty((h, w), np.float32)
                run._check(run.dll.live_shift_snapshot(run.handle, shift.ctypes.data))
                assert np.isfinite(shift).all()
                shifts[variant] = cv2.resize(shift, reduced, interpolation=cv2.INTER_AREA)
                image = np.empty((h, w*2, 4), np.uint8)
                run.pool.check(run.pool.dll.live_pool_readback(run.pool.handle, 0, image.ctypes.data))
                eyes[variant] = image
                if review:
                    movies[variant].write(memoryview(image).cast('B'))
            # Per-eye shift residual on RGB edges after backward motion alignment.
            if previous is not None and not row['cut']:
                back = flow.calc(gray, prior_gray, None)
                mx, my = xx + back[:, :, 0], yy + back[:, :, 1]
                valid = (mx >= 1) & (my >= 1) & (mx < reduced[0]-1) & (my < reduced[1]-1)
                valid &= cv2.absdiff(gray, cv2.remap(prior_gray, mx, my, cv2.INTER_LINEAR)) < 8
                valid &= cv2.resize(edge.astype(np.uint8)*255, reduced, interpolation=cv2.INTER_AREA) >= 64
                if valid.any():
                    for variant in variants:
                        warped = cv2.remap(previous[variant], mx, my, cv2.INTER_LINEAR)
                        row[f'edge_residual{variant}'] = float(cv2.absdiff(shifts[variant], warped)[valid].mean())
            # Full-resolution output difference; measure both eyes on the same source coordinates.
            diff = cv2.absdiff(eyes[variants[0]], eyes[variants[1]])[:, :, :3].max(axis=2)
            row['changed_over3'] = float((diff > 3).mean())
            row['edge_over3'] = float(((diff[:, :w][edge] > 3).mean() + (diff[:, w:][edge] > 3).mean()) / 2)
            if i == count//2:
                # One difficult crop for inspection, chosen by greatest left-eye difference.
                grid = cv2.resize(diff[:, :w], (12, 8), interpolation=cv2.INTER_AREA)
                gy, gx = np.unravel_index(grid.argmax(), grid.shape)
                x = min(w-384, max(0, int((gx+.5)*w/12)-192))
                y = min(h-216, max(0, int((gy+.5)*h/8)-108))
                crops = [eyes[r][y:y+216, x:x+384, :3] for r in variants]
                bgr = cv2.cvtColor(np.hstack(crops), cv2.COLOR_RGB2BGR)
                assert cv2.imwrite(str(out / f'{name}-{mode}-{variants[0]}-left_{variants[1]}-right.png'), bgr)
            previous, prior_gray = shifts, gray
            rows.append(row)
    warm = rows[6:]
    summary = dict(clip=name, mode=mode, frames=len(rows), size=[w, h])
    for r in variants:
        summary[f'guide_ms{r}'] = float(np.median([row[f'ms{r}'] for row in warm]))
        summary[f'edge_px{r}'] = float(np.mean([row[f'edge_residual{r}'] for row in warm if f'edge_residual{r}' in row]))
    for k in ('changed_over3','edge_over3'):
        summary[k] = float(np.mean([row[k] for row in warm]))
    return dict(summary=summary, rows=rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--review', action='store_true', help='Export 3 s of matched Base Jockey Full SBS for the display')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    configure_resource_root(BUNDLE)
    cv2.setNumThreads(2)
    runtime = Path('C:/TensorRT/TensorRT-11.2.1.2/bin')
    with os.add_dll_directory(str(runtime)):
        if args.review:
            run_case('Jockey', 'balanced', 180, args.output, runtime, review=True)
            return
        for name in (*HFR, *SOURCES):
            for mode in ('balanced','performance'):
                case = run_case(name, mode, 48, args.output, runtime)
                print(json.dumps(case['summary']), flush=True)
                (args.output / f'{name}-{mode}.json').write_text(json.dumps(case, indent=2))


if __name__ == '__main__':
    main()
