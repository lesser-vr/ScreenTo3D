"""Bounded MoGe-2 Small evaluation; no application loader/default changes.

Run with the isolated moge-source/moge-python-deps on PYTHONPATH.
"""
import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import subprocess
import time

import cv2
import numpy as np
import torch

from compare_small_aspect import Engine, digest, preprocess, ROOT
from public_test_media import SOURCES

SOURCE_REV = '74fbce054ebed49800de42d0ad0e83495065719a'
WEIGHT_REV = '26b477f41595707c5db6770294c0d1721e8ed4ed'
WEIGHT_HASH = '79a16621928c2bf0ed04659218c55c01075e950507f40bb3332fb4c873d3e1dc'
BASE_HASH = 'b0b6b745e9c3bd00317248bed833eee0d689ceeaaa11bb08a79d73d6531855c8'


def inverse_depth(depth, mask):
    valid = mask & np.isfinite(depth) & (depth > 0)
    if not valid.any():
        raise ValueError('No valid MoGe geometry')
    result = np.zeros_like(depth, dtype=np.float32)
    np.divide(1., depth, out=result, where=valid)
    if not np.isfinite(result).all():
        raise ValueError('Invalid inverse depth')
    return result[None], float(valid.mean())


def write_image(path, rgb):
    if not cv2.imwrite(str(path), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)):
        raise RuntimeError('Image write failed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--frames', type=int, default=30)
    parser.add_argument('--motion', action='store_true', help='Compare DA2 with FP16/1200 and encode 60 Hz SBS clips')
    args = parser.parse_args()
    if not 5 <= args.frames <= (360 if args.motion else 60):
        raise ValueError('Frame count outside bounded experiment')
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(status='incomplete', cases=[], timing=[], sources=SOURCES,
                  source_revision=SOURCE_REV, weight_revision=WEIGHT_REV,
                  weight_sha256=WEIGHT_HASH, baseline_engine_sha256=BASE_HASH,
                  input_hw=[2160, 3840], moge_input_hw=[392, 700],
                  baseline_input_hw=[518, 518], frames_per_source=args.frames,
                  contract='Same source frame and stereo policy. MoGe official PyTorch '
                  'FP32 or autocast FP16 vs existing DA2 TensorRT FP32: implementation '
                  'comparison, NOT equal-runtime architecture speed comparison. '
                  'MoGe mask invalids become far inverse depth zero. Independent EMA. '
                  'No ground truth, capture, FG, native display, HMD or support claim.',
                  visual_review='pending', selection='not_promoted')
    report['motion'] = args.motion
    report['videos'] = []
    engine = None
    try:
        src = ROOT/'out/moge-source'
        assert subprocess.check_output(['git', '-C', str(src), 'rev-parse', 'HEAD'], text=True).strip() == SOURCE_REV
        assert not subprocess.check_output(['git', '-C', str(src), 'status', '--porcelain'], text=True).strip()
        weight = ROOT/'out/models/moge-2-small/model.pt'
        assert digest(weight) == WEIGHT_HASH
        baseline = ROOT/'out/p1-distill-small-20260909/da2-small-fp32.plan'
        assert digest(baseline) == BASE_HASH
        from moge.model.v2 import MoGeModel
        from screento3d_app.pipeline import StereoSynthesizer
        from screento3d_app.live_policy import resolve_live
        from screento3d_app.live_projection import LiveProjection
        torch.set_num_threads(1)
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        start = time.perf_counter()
        model = MoGeModel.from_pretrained(weight).cuda().eval()
        torch.cuda.synchronize()
        report['model_load_seconds'] = time.perf_counter()-start
        report['environment'] = dict(torch=torch.__version__, numpy=np.__version__,
                                      gpu=torch.cuda.get_device_name(), tf32=False)
        report['parameters'] = sum(p.numel() for p in model.parameters())
        variants = {'moge-fp32-1200': (1200, False),
                    'moge-fp16-1200': (1200, True), 'moge-fp16-1800': (1800, True)}
        if args.motion:
            variants = {'moge-fp16-1200': (1200, True)}
            from distill_gpu_motion import Encoder
            from screento3d_app.desktop_jobs import BUNDLE
            ffmpeg, ffprobe = BUNDLE/'ffmpeg/ffmpeg.exe', BUNDLE/'ffmpeg/ffprobe.exe'
            report['motion_contract'] = ('60 Hz source/output timestamps, every frame inferred; '
                'offline host normalization/guidance plus paired CUDA projection, not the '
                'production all-GPU postprocessor. No real-time claim. No audio copied. '
                'Flow proxy: 350x196 backward Farneback, in-bounds and RGB residual <20/255; '
                'absolute normalized-depth residual, not ground truth or flicker acceptance.')
        with os.add_dll_directory('C:/TensorRT/TensorRT-11.2.1.2/bin'), LiveProjection(3840, 2160) as projection:
            import tensorrt as trt
            engine = Engine(baseline, (518, 518), trt, torch, trt.Logger(trt.Logger.WARNING))
            for source, expected in SOURCES.items():
                path = ROOT/'out/public-video-source/uvg-vcm'/f'{source}.mp4'
                assert digest(path) == expected
                cap = cv2.VideoCapture(str(path))
                if abs(cap.get(cv2.CAP_PROP_FPS)-60) > .001:
                    cap.release()
                    raise ValueError('Expected exact 60 Hz public source')
                names = ['da2-trt-fp32', *variants]
                synths = {name: StereoSynthesizer(3840, 2160, resolve_live('performance'),
                          projection, paired_projection=projection.project_pair) for name in names}
                previous = {}
                previous_gray = None
                encoders = {}
                completed = False
                crops = {'FloorballGame': (1150, 850), 'OfficeWalk': (1500, 900), 'ParkingGarage': (1450, 750)}
                owned = ExitStack()
                try:
                    if args.motion:
                        for name in names:
                            encoders[name] = Encoder(ffmpeg, args.output/f'{source}-{name}.partial.mp4')
                            owned.callback(lambda enc=encoders[name]: enc.close(failed=not completed))
                    for index in range(args.frames):
                        ok, bgr = cap.read()
                        assert ok and bgr.shape == (2160, 3840, 3)
                        frame = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                        small = cv2.resize(frame, (700, 392), interpolation=cv2.INTER_CUBIC)
                        inp = torch.from_numpy(small.copy()).permute(2, 0, 1).float().cuda()/255
                        base_inp = preprocess(frame, (518, 518))
                        gray = cv2.cvtColor(cv2.resize(frame, (350, 196)), cv2.COLOR_RGB2GRAY)
                        flow_map = reliable = None
                        if args.motion and previous_gray is not None:
                            flow = cv2.calcOpticalFlowFarneback(gray, previous_gray, None, .5, 3, 15, 3, 5, 1.2, 0)
                            yy, xx = np.mgrid[:196, :350].astype(np.float32)
                            flow_map = (xx+flow[..., 0], yy+flow[..., 1])
                            warped = cv2.remap(previous_gray, *flow_map, cv2.INTER_LINEAR)
                            reliable = ((flow_map[0] >= 0) & (flow_map[0] <= 349) &
                                        (flow_map[1] >= 0) & (flow_map[1] <= 195) &
                                        (np.abs(gray.astype(np.float32)-warped) < 20))
                        def infer(name):
                            if name == 'da2-trt-fp32':
                                return engine.infer(base_inp)[0], 1.0
                            tokens, fp16 = variants[name]
                            output = model.infer(inp, num_tokens=tokens, use_fp16=fp16)
                            return inverse_depth(output['depth'].cpu().numpy(), output['mask'].cpu().numpy())
                        if index == 0:
                            for name in names:
                                for _ in range(3):
                                    infer(name)
                                for repeat in range(5):
                                    torch.cuda.synchronize()
                                    start = time.perf_counter()
                                    infer(name)
                                    torch.cuda.synchronize()
                                    report['timing'].append(dict(source=source, model=name, repeat=repeat,
                                         infer_post_readback_ms=(time.perf_counter()-start)*1000))
                        tiles = [cv2.resize(frame, (700, 392))]
                        crop_rows = {}
                        for name in (names if index % 2 == 0 else names[::-1]):
                            started = time.perf_counter()
                            depth, coverage = infer(name)
                            assert depth.ndim == 3 and np.isfinite(depth).all()
                            sbs = synths[name].render(frame, depth)
                            processing_ms = (time.perf_counter()-started)*1000
                            assert sbs.shape == (2160, 7680, 3)
                            norm = cv2.resize(synths[name].smoothed_depth, (700, 392))
                            row = dict(source=source, frame=index, model=name, valid_fraction=coverage,
                                       processing_ms=processing_ms)
                            if name in previous:
                                row['normalized_change_mae'] = float(np.abs(norm-previous[name]).mean())
                                if flow_map is not None and reliable.any():
                                    old = cv2.resize(previous[name], (350, 196))
                                    aligned = cv2.remap(old, *flow_map, cv2.INTER_LINEAR)
                                    residual = np.abs(cv2.resize(norm, (350, 196))-aligned)
                                    row['flow_residual_mae'] = float(residual[reliable].mean())
                                    row['flow_reliable_fraction'] = float(reliable.mean())
                            previous[name] = norm.copy()
                            report['cases'].append(row)
                            if args.motion:
                                encoders[name].write(sbs)
                                if index % 60 == 0 or index == args.frames-1:
                                    x, y = crops[source]
                                    crop = np.hstack([sbs[y:y+384, x+offset:x+offset+384] for offset in (0, 3840)]).copy()
                                    cv2.putText(crop, f'{name} f{index}: left | right', (5, 24),
                                                cv2.FONT_HERSHEY_SIMPLEX, .6, (255, 60, 60), 2)
                                    crop_rows[name] = crop
                            if index in (0, args.frames-1):
                                write_image(args.output/f'{source}-{index}-{name}-sbs.png', sbs)
                                np.save(args.output/f'{source}-{index}-{name}-inverse.npy', depth)
                        if index in (0, args.frames-1) or (args.motion and index % 60 == 0):
                            for name in names:
                                tile = np.repeat((np.clip(previous[name], 0, 1)*255).astype(np.uint8)[..., None], 3, axis=2)
                                cv2.putText(tile, name, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, .7, (255, 80, 80), 2)
                                tiles.append(tile)
                            write_image(args.output/f'{source}-{index}-comparison.jpg', np.vstack(tiles))
                        if crop_rows:
                            write_image(args.output/f'{source}-{index}-eye-crops.jpg', np.vstack([crop_rows[name] for name in names]))
                        previous_gray = gray
                        if index % (30 if args.motion else 10) == 0:
                            print(source, index, 'valid', flush=True)
                    completed = True
                finally:
                    cap.release()
                    owned.close()
                if args.motion:
                    for name in names:
                        pending = args.output/f'{source}-{name}.partial.mp4'
                        stream = json.loads(subprocess.check_output([str(ffprobe), '-v', 'error',
                            '-select_streams', 'v:0', '-count_frames', '-show_streams', '-of', 'json', str(pending)],
                            timeout=120))['streams'][0]
                        if ((stream['width'], stream['height'], int(stream['nb_read_frames'])) !=
                                (7680, 2160, args.frames) or stream['r_frame_rate'] != '60/1'):
                            raise RuntimeError('Encoded geometry/frame count/rate mismatch')
                        subprocess.run([str(ffmpeg), '-v', 'error', '-xerror', '-i', str(pending),
                                        '-f', 'null', '-'], check=True, timeout=120)
                        report['videos'].append(dict(path=str(pending), frames=args.frames, decoded=True))
                    (args.output/'partial.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            report['projection'] = projection.telemetry()
        report['peak_allocated_mib'] = torch.cuda.max_memory_allocated()/1024**2
        report['summary'] = {}
        for name in names:
            values = [r['infer_post_readback_ms'] for r in report['timing'] if r['model'] == name]
            report['summary'][name] = dict(median_ms=float(np.median(values)), min_ms=min(values), max_ms=max(values))
        for video in report['videos']:
            pending = Path(video['path'])
            final = pending.with_name(pending.name.replace('.partial', ''))
            if final.exists():
                raise FileExistsError(final)
            pending.rename(final)
            video.update(path=str(final), sha256=digest(final))
        report['status'] = 'measured'
    finally:
        if engine is not None:
            engine.close()
        report['script_sha256'] = digest(Path(__file__))
        (args.output/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report['summary'], indent=2), flush=True)


if __name__ == '__main__':
    main()
