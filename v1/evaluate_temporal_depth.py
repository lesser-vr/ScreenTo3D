"""Bounded synthetic-ground-truth and real-model evaluation of one-frame history."""
import argparse
import json
import os
from pathlib import Path
import time

import cv2
import numpy as np

from compare_small_aspect import digest, preprocess
from distill_gpu_motion import local_engine
from distill_small_experiment import ROOT
from temporal_depth_experiment import MotionDepth


def baseline_blend(current, previous, frame, old_frame):
    if previous is None:
        return current.copy()
    changed = np.max(np.abs(frame.astype(np.float32)-old_frame.astype(np.float32)), axis=2)/255 > .04
    changed = cv2.dilate(changed.astype(np.uint8), np.ones((7, 7), np.uint8)) != 0
    changed |= np.abs(current-previous) > .08
    return np.where(changed, current, .55*current+.45*previous).astype(np.float32)


def synthetic(output):
    rng = np.random.default_rng(4931)
    h, w, count = 180, 320, 90
    world = rng.integers(30, 225, (h, w+count*2, 3), np.uint8)
    world = cv2.GaussianBlur(world, (3, 3), 0)
    y, x = np.indices(world.shape[:2], dtype=np.float32)
    truth = (.15+.3*x/world.shape[1]+.1*y/h).astype(np.float32)
    truth[40:145, 130:200] = .85
    model = MotionDepth()
    previous = old_frame = None
    baseline_errors, candidate_errors, ages, accepted = [], [], [], []
    cut_exact = False
    for index in range(count):
        frame = world[:, index*2:index*2+w].copy()
        clean = truth[:, index*2:index*2+w].copy()
        if index >= 45:
            frame = 255-frame
            clean = 1-clean
        noisy = np.clip(clean+rng.normal(0, .005, clean.shape), 0, 1).astype(np.float32)
        if index == 45:
            previous = old_frame = None
        baseline = baseline_blend(noisy, previous, frame, old_frame)
        candidate, stats = model.update(frame, noisy, index, round(index*1e9/60), cut=index==45)
        if index == 45:
            cut_exact = np.array_equal(candidate, noisy)
        if index not in (0, 45):
            baseline_errors.append(float(np.abs(baseline-clean).mean()))
            candidate_errors.append(float(np.abs(candidate-clean).mean()))
            ages.append(stats['maximum_history_age_ns'])
            accepted.append(stats['accepted_fraction'])
        previous, old_frame = baseline, frame
    base, candidate = float(np.mean(baseline_errors)), float(np.mean(candidate_errors))
    return dict(frames=count, noise_sigma=.005, seed=4931, cut_frame=45,
                baseline_mae=base, candidate_mae=candidate, cut_exact=cut_exact,
                maximum_age_ns=max(ages), mean_accepted=float(np.mean(accepted)),
                gate='At least 5% ground-truth MAE reduction, exact cut fallback, history <= one 60Hz frame',
                passed=candidate <= base*.95 and cut_exact and max(ages) <= 16_666_667)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    cv2.setNumThreads(1)
    report = dict(status='incomplete', synthetic=synthetic(args.output), natural=[],
                  scope='Normalized model-grid prototype, not a change to production GPU filtering. '
                  'Same-frame and motion-aligned comparisons use fresh depth on every frame. '
                  'Natural metrics have no ground truth and do not certify quality or FPS.',
                  model='Distill FP32', input=[3840, 2160], model_grid=[518, 518])
    print('SYNTHETIC', report['synthetic'], flush=True)
    from public_test_media import SOURCES
    with os.add_dll_directory('C:/TensorRT/TensorRT-11.2.1.2/bin'):
        with local_engine('distill') as engine:
            for source, expected in SOURCES.items():
                path = ROOT/'out/public-video-source/uvg-vcm'/f'{source}.mp4'
                if digest(path) != expected:
                    raise ValueError('Public source changed')
                capture = cv2.VideoCapture(str(path))
                motion = MotionDepth()
                low = high = previous = old_frame = old_candidate = None
                try:
                    for index in range(180):
                        ok, bgr = capture.read()
                        if not ok or bgr.shape != (2160, 3840, 3):
                            raise ValueError('Unexpected public source')
                        frame = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                        raw = engine.infer(preprocess(frame, (518, 518)))[0]
                        lo, hi = np.percentile(raw, [2, 98])
                        low = lo if low is None else .55*lo+.45*low
                        high = hi if high is None else .55*hi+.45*high
                        current = np.clip((raw-low)/max(high-low, 1e-6), 0, 1).astype(np.float32)
                        small = cv2.resize(frame, (518, 518), interpolation=cv2.INTER_AREA)
                        baseline = baseline_blend(current, previous, small, old_frame)
                        started = time.perf_counter_ns()
                        candidate, stats = motion.update(frame, current, index, round(index*1e9/60))
                        row = dict(source=source, frame=index, temporal_ms=(time.perf_counter_ns()-started)/1e6,
                                   **stats, candidate_vs_current_mae=float(np.abs(candidate-current).mean()),
                                   candidate_vs_baseline_mae=float(np.abs(candidate-baseline).mean()))
                        if previous is not None:
                            row['baseline_change'] = float(np.abs(baseline-previous).mean())
                            row['candidate_change'] = float(np.abs(candidate-old_candidate).mean())
                        report['natural'].append(row)
                        if index in (0, 60, 120, 179):
                            tiles = [cv2.resize(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR), (518, 518))]
                            for label, depth in [('current', current), ('same-frame EMA', baseline), ('motion history', candidate)]:
                                tile = cv2.cvtColor(np.uint8(np.clip(depth, 0, 1)*255), cv2.COLOR_GRAY2BGR)
                                cv2.putText(tile, label, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, .65, (0, 0, 255), 1)
                                tiles.append(tile)
                            if not cv2.imwrite(str(args.output/f'{source}-{index}.png'), np.hstack(tiles)):
                                raise RuntimeError('Review image failed')
                        previous, old_frame, old_candidate = baseline, small, candidate
                        if index % 60 == 0:
                            print(source, index, round(row['temporal_ms'], 2), flush=True)
                finally:
                    capture.release()
    report['status'] = 'measured'
    report['script_sha256'] = digest(__file__)
    report['prototype_sha256'] = digest(ROOT/'v1/temporal_depth_experiment.py')
    (args.output/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('MEASURED', args.output/'report.json', flush=True)


if __name__ == '__main__':
    main()
