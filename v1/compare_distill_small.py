"""Controlled model A/B on public native-4K frames; no app/default promotion."""
import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import time

import cv2
import numpy as np

from compare_small_aspect import Engine, digest, preprocess
from distill_small_experiment import load_model, ROOT


def oracle_error(reference, actual):
    if reference.shape != actual.shape or not (np.isfinite(reference).all()
                                               and np.isfinite(actual).all()):
        raise ValueError('Invalid reference output')
    error = np.abs(reference - actual)
    return dict(maximum=float(error.max()), mae=float(error.mean()),
                passed=bool(np.allclose(reference, actual, atol=.001, rtol=.001)))


def save_rgb(path, rgb):
    if not cv2.imwrite(str(path), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)):
        raise RuntimeError('Failed to save review image')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--frames', type=int, default=30)
    args = parser.parse_args()
    if not 6 <= args.frames <= 60:
        raise ValueError('Frames must be 6..60 per source')
    directory = args.directory.resolve(strict=True)
    output = directory / 'comparison'
    output.mkdir(exist_ok=False)
    report = dict(status='incomplete', frames_per_source=args.frames, cases=[], sources={},
                  input=[3840, 2160], per_eye=[3840, 2160], combined=[7680, 2160],
                  input_hz=60, model_input_hw=[518, 518], runtime='TRT FP32, TF32 disabled',
                  visual_review='pending', selection='not_promoted',
                  oracle_contract=dict(atol=.001, rtol=.001),
                  comparison_contract='Same RGB cubic uint8 resize/normalization, shape and '
                  'FP32/TF32-disabled runtime. Same Performance stereo policy and paired '
                  'CUDA renderer, independent per-model normalization/EMA; no frame reuse. '
                  'Raw depth differs intentionally; no reference ground truth. '
                  'Temporal change is a proxy, not flicker or motion accuracy acceptance.',
                  scope='Offline bounded evaluation with real 4K SBS stills. '
                  'No capture, live output, FG, scanout, HMD or real-time support claim.')
    export = json.loads((directory / 'export.json').read_text())
    if digest(directory / 'distill-small-fp32.onnx') != export['onnx_sha256']:
        raise ValueError('Export changed')
    baseline = ROOT / 'out/models/da2-small/model_fp32.onnx'
    baseline_manifest = json.loads((ROOT/'models/da2-small/fp32-reference-manifest.json').read_text())
    if digest(baseline) != baseline_manifest['sha256']:
        raise ValueError('Baseline changed')
    report['provenance'] = export
    report['baseline_onnx_sha256'] = digest(baseline)
    import torch
    import onnxruntime as ort
    from public_test_media import SOURCES
    from depthsbs_app.pipeline import StereoSynthesizer
    from depthsbs_app.live_policy import resolve_live
    from depthsbs_app.live_projection import LiveProjection, DLL_SHA256
    torch.set_num_threads(1)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    options = ort.SessionOptions()
    options.intra_op_num_threads = 4
    reference = ort.InferenceSession(str(baseline), sess_options=options,
                                    providers=['CPUExecutionProvider'])
    model = None
    try:
        model, _ = load_model()
        report['environment'] = dict(gpu=torch.cuda.get_device_name(), torch=torch.__version__,
                                      projection_sha256=DLL_SHA256,
                                      torch_cpu_threads=1, ort_cpu_threads=4)
        with os.add_dll_directory('C:/TensorRT/TensorRT-11.2.1.2/bin'), ExitStack() as owned:
            import tensorrt as trt
            report['environment']['tensorrt'] = trt.__version__
            logger = trt.Logger(trt.Logger.WARNING)
            engines = {}
            report['engine_hashes'] = {}
            for name in ('da2', 'distill'):
                path = directory / f'{name}-small-fp32.plan'
                report['engine_hashes'][name] = digest(path)
                engines[name] = Engine(path, (518, 518), trt, torch, logger)
                owned.callback(engines[name].close)
            projection = owned.enter_context(LiveProjection(3840, 2160))
            policy = resolve_live('performance')
            for source, expected in SOURCES.items():
                path = ROOT/'out/public-video-source/uvg-vcm'/f'{source}.mp4'
                if digest(path) != expected:
                    raise ValueError('Public source changed')
                report['sources'][source] = expected
                synths = {name: StereoSynthesizer(3840, 2160, policy, projection,
                          paired_projection=projection.project_pair) for name in engines}
                previous = {}
                capture = cv2.VideoCapture(str(path))
                try:
                    for index in range(args.frames):
                        ok, bgr = capture.read()
                        if not ok or bgr.shape != (2160, 3840, 3):
                            raise ValueError('Expected native-4K public frames')
                        frame = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                        tensor = preprocess(frame, (518, 518))
                        rows, depths = [], {}
                        for name in (('da2', 'distill') if index % 2 == 0 else ('distill', 'da2')):
                            engine = engines[name]
                            if index == 0:
                                for _ in range(10):
                                    engine.infer(tensor)
                            started = time.perf_counter_ns()
                            depth, gpu_ms = engine.infer(tensor)
                            row = dict(source=source, frame=index, model=name, gpu_ms=gpu_ms,
                                       inference_io_ms=(time.perf_counter_ns()-started)/1e6)
                            if index in (0, args.frames-1):
                                if name == 'distill':
                                    with torch.inference_mode():
                                        expected_depth = model(torch.from_numpy(tensor).cuda()).cpu().numpy()
                                else:
                                    expected_depth = reference.run(['predicted_depth'], {'pixel_values': tensor})[0]
                                row['oracle'] = oracle_error(expected_depth, depth)
                                if not row['oracle']['passed']:
                                    raise RuntimeError(f'Numerical gate failed: {source}/{name}/{index}: {row}')
                            depths[name] = depth
                            rows.append(row)
                        for row in rows:
                            name = row['model']
                            started = time.perf_counter_ns()
                            sbs = synths[name].render(frame, depths[name])
                            row['stereo_host_ms'] = (time.perf_counter_ns()-started)/1e6
                            if sbs.shape != (2160, 7680, 3):
                                raise ValueError('SBS geometry mismatch')
                            normalized = synths[name].smoothed_depth
                            if name in previous:
                                row['normalized_depth_change_mae'] = float(np.abs(normalized-previous[name]).mean())
                            previous[name] = normalized.copy()
                            if index in (0, args.frames-1):
                                save_rgb(output/f'{source}-{index}-{name}-sbs.png', sbs)
                        if index in (0, args.frames-1):
                            tiles = [cv2.resize(bgr, (960, 540))]
                            for name in ('da2', 'distill'):
                                gray = np.uint8(np.clip(synths[name].smoothed_depth, 0, 1)*255)
                                tile = cv2.resize(cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR), (960, 540))
                                cv2.putText(tile, name, (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                                tiles.append(tile)
                            if not cv2.imwrite(str(output/f'{source}-{index}-depth.png'), np.hstack(tiles)):
                                raise RuntimeError('Depth preview failed')
                        report['cases'].extend(rows)
                        if index % 10 == 0 or index == args.frames-1:
                            print(source, index, 'passed', flush=True)
                finally:
                    capture.release()
                (output/'partial.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            report['projection'] = projection.telemetry()
    finally:
        if model is not None:
            torch.cuda.synchronize()
            del model
    report['status'] = 'measured'
    report['oracle_passed'] = all(row['oracle']['passed'] for row in report['cases'] if 'oracle' in row)
    report['script_sha256'] = digest(__file__)
    (output/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('MEASURED', output/'report.json', flush=True)


if __name__ == '__main__':
    main()
