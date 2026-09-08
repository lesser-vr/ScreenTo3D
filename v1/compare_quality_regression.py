"""Bounded matched SBS comparison; metrics and review frames never certify perceptual quality."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import subprocess

import cv2
import numpy as np


CONTRACT_SCHEMA = 'depthsbs.matched-quality-comparison.v1'
RATE_KEYS = ('capture_hz', 'model_input_hz', 'fresh_depth_hz', 'base_sbs_hz', 'generated_output_hz')
REVIEW_KEYS = ('spatial_depth', 'temporal_stability', 'occlusion_edges', 'text', 'cuts',
               'binocular_consistency', 'game_latency')
REVIEW_VALUES = {'baseline', 'candidate', 'tie', 'inconclusive', 'pending', 'not_applicable'}


def _nonempty(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{label} must be a nonempty string')
    return value.strip()


def _positive_rate(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value) or value <= 0:
        raise ValueError(f'{label} must be a finite positive number')
    return float(value)


def validate_comparison_contract(contract, geometry):
    """Validate reproducibility metadata without turning review into an automated quality verdict."""
    if not isinstance(contract, dict) or contract.get('schema') != CONTRACT_SCHEMA:
        raise ValueError(f'comparison contract schema must be {CONTRACT_SCHEMA}')
    workload = contract.get('workload')
    if not isinstance(workload, dict) or workload.get('kind') not in {'game', 'video'}:
        raise ValueError('workload.kind must be game or video')
    _nonempty(workload.get('name'), 'workload.name')
    _nonempty(workload.get('source_identity'), 'workload.source_identity')

    environment = contract.get('environment')
    if not isinstance(environment, dict):
        raise ValueError('environment must be an object')
    for key in ('gpu', 'driver', 'display', 'power', 'competing_gpu_workloads'):
        _nonempty(environment.get(key), f'environment.{key}')

    declared_geometry = contract.get('geometry')
    if not isinstance(declared_geometry, dict):
        raise ValueError('geometry must be an object')
    for key in ('input', 'per_eye', 'combined'):
        value = declared_geometry.get(key)
        if (not isinstance(value, list) or len(value) != 2 or
                any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in value)):
            raise ValueError(f'geometry.{key} must be [positive width, positive height]')
        if value != geometry[key]:
            raise ValueError(f'geometry.{key} does not match probed media')

    paths = contract.get('paths')
    if not isinstance(paths, dict):
        raise ValueError('paths must be an object')
    normalized_paths = {}
    latency_status = {}
    for path_name in ('baseline', 'candidate'):
        path = paths.get(path_name)
        if not isinstance(path, dict):
            raise ValueError(f'paths.{path_name} must be an object')
        descriptions = {key: _nonempty(path.get(key), f'paths.{path_name}.{key}')
                        for key in ('label', 'model', 'postprocessing', 'frame_generation')}
        rates = path.get('rates')
        if not isinstance(rates, dict):
            raise ValueError(f'paths.{path_name}.rates must be an object')
        values = {key: _positive_rate(rates.get(key), f'paths.{path_name}.rates.{key}') for key in RATE_KEYS}
        if not (values['fresh_depth_hz'] <= values['model_input_hz'] <= values['capture_hz'] and
                values['base_sbs_hz'] <= values['capture_hz'] and
                values['base_sbs_hz'] <= values['generated_output_hz']):
            raise ValueError(f'paths.{path_name}.rates has inconsistent pipeline ordering')
        latency = path.get('latency')
        if not isinstance(latency, dict) or latency.get('status') not in {'pending', 'measured'}:
            raise ValueError(f'paths.{path_name}.latency.status must be pending or measured')
        latency_status[path_name] = latency['status']
        if latency['status'] == 'measured':
            method = _nonempty(latency.get('method'), f'paths.{path_name}.latency.method')
            values_ms = []
            for key in ('p50_ms', 'p95_ms', 'p99_ms'):
                value = latency.get(key)
                if (isinstance(value, bool) or not isinstance(value, (int, float)) or
                        not np.isfinite(value) or value < 0):
                    raise ValueError(f'paths.{path_name}.latency.{key} must be finite and nonnegative')
                values_ms.append(float(value))
            if values_ms != sorted(values_ms):
                raise ValueError(f'paths.{path_name}.latency percentiles must be ordered')
            normalized_latency = dict(status='measured', method=method,
                                      p50_ms=values_ms[0], p95_ms=values_ms[1], p99_ms=values_ms[2])
        else:
            normalized_latency = dict(status='pending')
        normalized_paths[path_name] = dict(**descriptions, rates=values, latency=normalized_latency)

    review = contract.get('review')
    if not isinstance(review, dict):
        raise ValueError('review must be an object')
    for key in REVIEW_KEYS:
        if review.get(key) not in REVIEW_VALUES:
            raise ValueError(f'review.{key} must be one of {sorted(REVIEW_VALUES)}')
    if workload['kind'] == 'game' and review['game_latency'] == 'not_applicable':
        raise ValueError('review.game_latency cannot be not_applicable for a game')
    comparison_ready = all(review[key] not in {'pending', 'inconclusive'} for key in REVIEW_KEYS)
    if workload['kind'] == 'game' and any(value != 'measured' for value in latency_status.values()):
        comparison_ready = False
    return dict(schema=CONTRACT_SCHEMA,
                workload=dict(kind=workload['kind'], name=workload['name'].strip(),
                              source_identity=workload['source_identity'].strip()),
                environment={key: environment[key].strip() for key in
                             ('gpu', 'driver', 'display', 'power', 'competing_gpu_workloads')},
                geometry={key: list(declared_geometry[key]) for key in ('input', 'per_eye', 'combined')},
                paths=normalized_paths, review=dict(review), comparison_ready=comparison_ready)


def frame_metrics(baseline, candidate, previous_baseline=None, previous_candidate=None):
    if (baseline.shape != candidate.shape or baseline.ndim != 3 or
            baseline.shape[0] < 1 or baseline.shape[1] < 2 or baseline.shape[1] % 2 or
            baseline.shape[2] != 3 or baseline.dtype != np.uint8 or candidate.dtype != np.uint8):
        raise ValueError('Matched even-width SBS frames are required')
    error = np.abs(baseline.astype(np.float32) - candidate.astype(np.float32)) / 255
    middle = baseline.shape[1] // 2
    result = dict(left_rgb_mae=float(error[:, :middle].mean()), right_rgb_mae=float(error[:, middle:].mean()))
    if previous_baseline is not None:
        before = np.abs(baseline.astype(np.float32) - previous_baseline.astype(np.float32)).mean() / 255
        after = np.abs(candidate.astype(np.float32) - previous_candidate.astype(np.float32)).mean() / 255
        result['temporal_change_increase'] = float(after - before)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--candidate', required=True, type=Path)
    parser.add_argument('--media-tools', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--contract', type=Path,
                        help='Reproducibility contract required for product-baseline claims')
    parser.add_argument('--frames', type=int, default=120)
    parser.add_argument('--max-rgb-mae', type=float)
    parser.add_argument('--max-temporal-change-increase', type=float)
    args = parser.parse_args()
    if not 1 <= args.frames <= 240:
        parser.error('frames must be 1..240')
    for threshold in (args.max_rgb_mae, args.max_temporal_change_increase):
        if threshold is not None and (not np.isfinite(threshold) or threshold < 0):
            parser.error('thresholds must be finite and nonnegative')
    args.output.mkdir(parents=True, exist_ok=False)
    def metadata(path):
        data = subprocess.check_output([str(args.media_tools/'ffprobe.exe'), '-v', 'error',
            '-select_streams', 'v:0', '-show_streams', '-of', 'json', str(path)], timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW)
        return json.loads(data)['streams'][0]
    report = dict(status='failed', visual_review='pending',
                  scope='Bounded RGB/temporal proxies and review frames; not depth accuracy, VR comfort or latency',
                  thresholds=dict(max_rgb_mae=args.max_rgb_mae, max_temporal_change_increase=args.max_temporal_change_increase))
    captures = []
    try:
        info = [metadata(path) for path in (args.source, args.baseline, args.candidate)]
        source = info[0]
        if not (16 <= source['width'] <= 4096 and 16 <= source['height'] <= 2160):
            raise ValueError('Comparison allocation bound is 16..4096 by 16..2160 per eye')
        for item in info[1:]:
            if (item['width'], item['height']) != (source['width']*2, source['height']):
                raise ValueError('SBS geometry does not preserve per-eye source dimensions')
            if Fraction(item['avg_frame_rate']) != Fraction(source['avg_frame_rate']):
                raise ValueError('Frame rates must match for frame-aligned comparison')
            if item.get('nb_frames') != source.get('nb_frames'):
                raise ValueError('Declared frame counts must match')
        report['artifacts'] = {}
        for name in ('source', 'baseline', 'candidate'):
            path = getattr(args, name)
            with path.open('rb') as stream:
                report['artifacts'][name] = dict(file=path.name, sha256=hashlib.file_digest(stream, 'sha256').hexdigest())
        report['geometry'] = dict(input=[source['width'], source['height']], per_eye=[source['width'], source['height']],
                                  combined=[info[1]['width'], info[1]['height']], fps=source['avg_frame_rate'])
        if args.contract is not None:
            contract = json.loads(args.contract.read_text(encoding='utf-8'))
            report['comparison_contract'] = validate_comparison_contract(contract, report['geometry'])
            with args.contract.open('rb') as stream:
                report['artifacts']['contract'] = dict(file=args.contract.name,
                    sha256=hashlib.file_digest(stream, 'sha256').hexdigest())
        captures = [cv2.VideoCapture(str(path), cv2.CAP_FFMPEG) for path in (args.baseline, args.candidate)]
        if not all(capture.isOpened() for capture in captures): raise ValueError('Cannot decode comparison inputs')
        rows, review = [], []
        previous = (None, None)
        limit = min(args.frames, int(source.get('nb_frames') or args.frames))
        for index in range(limit):
            decoded = [capture.read() for capture in captures]
            if decoded[0][0] != decoded[1][0]: raise ValueError('Different decoded frame counts')
            if not decoded[0][0]: break
            before, after = [item[1] for item in decoded]
            if any(frame.shape != (source['height'], source['width'] * 2, 3) for frame in (before, after)):
                raise ValueError('Decoded geometry differs from the declared SBS geometry')
            rows.append(dict(frame=index, **frame_metrics(before, after, *previous)))
            if index in {0, limit//2, limit-1}:
                def thumb(image, label):
                    value = cv2.resize(image, (640, max(32, round(image.shape[0]*640/image.shape[1]))))
                    value = cv2.copyMakeBorder(value, 24, 0, 0, 0, cv2.BORDER_CONSTANT)
                    cv2.putText(value, label, (6, 17), cv2.FONT_HERSHEY_SIMPLEX, .5, (255,255,255), 1)
                    return value
                review.append(np.vstack([thumb(before, f'baseline frame {index}'), thumb(after, f'candidate frame {index}')]))
            previous = (before, after)
        if not rows: raise ValueError('No comparison frames')
        if args.max_temporal_change_increase is not None and len(rows) < 2:
            raise ValueError('Temporal comparison needs at least two frames')
        worst_rgb = max(max(row['left_rgb_mae'], row['right_rgb_mae']) for row in rows)
        worst_temporal = max((row['temporal_change_increase'] for row in rows[1:]), default=0)
        passed = ((args.max_rgb_mae is None or worst_rgb <= args.max_rgb_mae) and
                  (args.max_temporal_change_increase is None or worst_temporal <= args.max_temporal_change_increase))
        report.update(status='measured' if passed else 'threshold_failed', compared_frames=len(rows), rows=rows,
                      rgb_mae_max=worst_rgb, temporal_change_increase_max=worst_temporal,
                      declared_thresholds_passed=passed if any(value is not None for value in
                          (args.max_rgb_mae, args.max_temporal_change_increase)) else None)
        if review and not cv2.imwrite(str(args.output/'review.png'), np.vstack(review)):
            raise RuntimeError('Could not write review frames')
    except Exception:
        report['status'] = 'failed'
        raise
    finally:
        for capture in captures: capture.release()
        (args.output/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return 0 if report['status'] == 'measured' else 1


if __name__ == '__main__':
    raise SystemExit(main())
