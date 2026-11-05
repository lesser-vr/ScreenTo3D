"""Matched-frame native texture RGB, disparity and temporal error diagnostic.

Full readback is intentionally outside the real-app throughput benchmark.
"""
import argparse
from contextlib import ExitStack
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import traceback

import cv2
import numpy as np
import torch

from base_trt_fp16_trial import installed, manifest
from depthsbs_app.da2_base import binding
from depthsbs_app.desktop_jobs import ROOT, BUNDLE
from depthsbs_app.gpu_frame import GpuFrame
from depthsbs_app.live_policy import resolve_live
from depthsbs_app.live_source_gpu_texture import LiveSourceGpuTexture
from depthsbs_app.resources import configure_resource_root
from depthsbs_app.stereo import refine_flat_background
from public_test_media import PublicFrames


def image_stats(error, width):
    absolute = np.abs(error)
    pixel = absolute.max(axis=2)
    return dict(rgb_mae=float(absolute.mean()), rgb_max=int(pixel.max()),
                left_mae=float(absolute[:, :width].mean()), right_mae=float(absolute[:, width:].mean()),
                pixels_gt8=float(np.mean(pixel > 8)), pixels_gt32=float(np.mean(pixel > 32)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sizes', default='1920x1080,3840x2160')
    parser.add_argument('--frames', type=int, default=60)
    args = parser.parse_args()
    if not 2 <= args.frames <= 120:
        raise ValueError('Use 2..120 consecutive public frames per clip')
    args.output.mkdir(parents=True, exist_ok=False)
    configure_resource_root(BUNDLE)
    cv2.setNumThreads(1)
    torch.set_num_threads(4)
    os.environ['DEPTHSBS_BASE_GRAPH'] = '0'
    os.environ['DEPTHSBS_BASE_INPUT'] = 'gpu'
    policy = replace(resolve_live('balanced'), depth_backend='da2-base')
    recipes = ('fp32', 'mixed', 'selective')
    report = dict(completed=False, policy=asdict(policy), plans=[manifest(r) for r in recipes],
                  scope='native texture readback with independent full live postprocessing histories; identical frame indices; no wall-clock FPS claim',
                  contract=dict(rgb_units='0..255 code values', pixel_thresholds=[8, 32],
                      disparity='effective postprocessed normalized depth difference * width * divergence; per-eye shift is half',
                      temporal='mean abs((candidate_t-control_t)-(candidate_previous-control_previous)) at fixed pixel coordinates; not flow-warped flicker',
                      edge='control SBS grayscale Sobel |dx|+|dy| >= 128',
                      cuts='shared input scene predicate; clip transitions and detected cuts reported separately',
                      acceptance='observational comparison, not a perceptual pass/fail or a changed parity tolerance'),
                  rows=[], sessions=[])
    def save():
        (args.output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    save()  # Persist metric definitions before observing any results.
    try:
        for size in args.sizes.split(','):
            width, height = map(int, size.split('x'))
            with ExitStack() as stack:
                runtime = Path('C:/TensorRT/TensorRT-11.2.1.2/bin')
                stack.enter_context(os.add_dll_directory(str(runtime)))
                renderers = {}
                for recipe in recipes:
                    with installed(recipe):
                        backend = binding(ROOT / 'out/da2-base-local', runtime, device_depth=True)
                        backend.input_validator(dict(width=width, height=height))
                        engine = stack.enter_context(backend.engine_factory(None))
                    renderers[recipe] = stack.enter_context(LiveSourceGpuTexture(width, height, policy, engine, diagnostic=True))
                previous_errors, previous_depth_errors = {}, {}
                previous_outputs = {}
                previous_label = None
                worst = {name: -1. for name in recipes[1:]}
                count = 0
                def process(rgb, label, group, index):
                    nonlocal count, previous_label
                    outputs, depths, cuts = {}, {}, {}
                    for name, renderer in renderers.items():
                        engine = renderer.engine
                        with torch.inference_mode(), torch.cuda.stream(engine.stream):
                            frame = GpuFrame(torch.from_numpy(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGRA)).cuda(), engine)
                        scene = renderer.inspect_scene(frame)
                        background = renderer.needs_background(frame)
                        token = renderer.infer(frame)
                        renderer.slot = count % 2
                        slot, aligned = renderer.render(frame, token, diagnostic=True, scene=scene)
                        readback = np.empty((height, width * 2, 4), np.uint8)
                        renderer.pool.check(renderer.pool.dll.live_pool_readback(renderer.pool.handle, slot, readback.ctypes.data))
                        if not np.all(readback[:, :, 3] == 255) or engine.pending_device is not None:
                            raise RuntimeError('Native output alpha/token completion failed')
                        if background:
                            aligned = refine_flat_background(rgb, aligned,
                                tolerance=policy.flat_background_tolerance,
                                minimum_coverage=policy.flat_background_min_coverage,
                                radius=policy.depth_guide_radius)
                        if not np.isfinite(aligned).all():
                            raise RuntimeError('Nonfinite effective depth')
                        outputs[name] = readback[:, :, :3].copy()
                        depths[name] = aligned
                        cuts[name] = scene.cut
                    if len(set(cuts.values())) != 1:
                        raise RuntimeError('Precision candidates disagree on RGB scene cuts')
                    control = outputs['fp32'].astype(np.int16)
                    gray = cv2.cvtColor(outputs['fp32'], cv2.COLOR_RGB2GRAY)
                    edge = (np.abs(cv2.Sobel(gray, cv2.CV_16S, 1, 0))
                            + np.abs(cv2.Sobel(gray, cv2.CV_16S, 0, 1))) >= 128
                    transition = previous_label is not None and previous_label != group
                    for name in recipes[1:]:
                        error = outputs[name].astype(np.int16) - control
                        depth_error = (depths[name] - depths['fp32']) * max(1., width * policy.divergence)
                        row = dict(size=size, label=label, group=group, index=index,
                                   cut=cuts[name], group_transition=transition,
                                   candidate=name, finite=True, **image_stats(error, width),
                                   edge_rgb_mae=float(np.abs(error)[edge].mean()) if edge.any() else None,
                                   disparity_mae_px=float(np.abs(depth_error).mean()),
                                   disparity_p99_px=float(np.percentile(np.abs(depth_error), 99)),
                                   disparity_max_px=float(np.abs(depth_error).max()))
                        if name in previous_errors:
                            row['temporal_rgb_error_mae'] = float(np.abs(error - previous_errors[name]).mean())
                            row['temporal_disparity_error_mae_px'] = float(np.abs(depth_error - previous_depth_errors[name]).mean())
                        if group == 'static' and previous_label == 'static':
                            row['static_candidate_change_mae'] = float(np.abs(outputs[name].astype(np.int16) - previous_outputs[name]).mean())
                            row['static_control_change_mae'] = float(np.abs(control - previous_outputs['fp32']).mean())
                        previous_errors[name], previous_depth_errors[name] = error, depth_error
                        report['rows'].append(row)
                        if row['rgb_mae'] > worst[name]:
                            worst[name] = row['rgb_mae']
                            folder = args.output / size / name
                            folder.mkdir(parents=True, exist_ok=True)
                            for filename, image in (('source', rgb), ('fp32', outputs['fp32']), ('candidate', outputs[name])):
                                if not cv2.imwrite(str(folder / f'{filename}.png'), cv2.cvtColor(image, cv2.COLOR_RGB2BGR)):
                                    raise RuntimeError('Review image save failed')
                            (folder / 'case.json').write_text(json.dumps(row, indent=2))
                    previous_outputs.update({name: value.astype(np.int16) for name, value in outputs.items()})
                    previous_label = group
                    count += 1
                for name in ('FloorballGame', 'OfficeWalk', 'ParkingGarage'):
                    for index, rgb in enumerate(PublicFrames(name, args.frames)):
                        rgb = cv2.resize(rgb, (width, height))
                        process(rgb, f'{name}-{index}', name, index)
                    print(f'{size}: compared {name}', flush=True)
                    save()
                # Cold-start static sequence: unchanged RGB, same inference/history policy.
                for renderer in renderers.values():
                    renderer.reset()
                previous_errors.clear()
                previous_depth_errors.clear()
                previous_outputs.clear()
                previous_label = None
                still = cv2.resize(next(iter(PublicFrames('OfficeWalk', 1))), (width, height))
                for index in range(12):
                    process(still, f'static-{index}', 'static', index)
                # Explicit high-contrast cuts, including flat-background refinement.
                for index, level in enumerate((0, 255, 0, 255)):
                    process(np.full((height, width, 3), level, np.uint8), f'cut-{index}', 'cut', index)
                for name, renderer in renderers.items():
                    report['sessions'].append(dict(size=size, candidate=name,
                        frames=renderer.frames, cpu_refinements=renderer.cpu_refinements,
                        engine=renderer.engine.telemetry(), pending_depth=renderer.engine.pending_device is not None))
            print(f'{size}: closed all engines and native pools', flush=True)
            save()
        report['completed'] = True
    except BaseException:
        report['error'] = traceback.format_exc()
        raise
    finally:
        save()
        print(args.output / 'report.json', flush=True)


if __name__ == '__main__':
    main()
