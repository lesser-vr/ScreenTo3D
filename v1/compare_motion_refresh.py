"""Controlled diagnostic A/B; never changes production policy or source media."""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
from unittest.mock import patch
import uuid
import numpy as np
from depthsbs_app import pipeline
from depthsbs_app.config import MODES
from quality_scenes import motion_frame


def without_motion(frame, inferred, index, policy, cut):
    if inferred is None:
        return 'initial'
    if index % policy.inference_cadence == 0:
        return 'cadence'
    return 'cut' if cut else 'reuse'


def synthetic_results():
    results = []
    for case in ('static', 'fast', 'small', 'low_contrast'):
        for enabled in (False, True):
            reference = depth = None
            stale_frames = inferences = max_wrong = 0
            for index in range(24):
                if case in ('static', 'fast'):
                    frame, current = motion_frame(index if case == 'fast' else 0, 160, 96)
                else:
                    frame = np.full((96, 160, 3), 40, np.uint8)
                    current = np.zeros((96, 160), np.float32)
                    left = 10 + (index * 12) % 120
                    size = 4 if case == 'small' else 20
                    frame[30:30+size, left:left+size] = 230 if case == 'small' else 48
                    current[30:30+size, left:left+size] = 1
                reason = (pipeline.depth_refresh_reason if enabled else without_motion)(
                    frame, reference, index, MODES['performance'], False)
                if reason != 'reuse':
                    reference, depth = frame, current
                    inferences += 1
                wrong = int(np.count_nonzero(depth != current))
                stale_frames += int(wrong > 0)
                max_wrong = max(max_wrong, wrong)
            results.append(dict(case=case, enabled=enabled, frames=24,
                inferences=inferences, stale_depth_frames=stale_frames,
                maximum_wrong_depth_pixels=max_wrong))
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--baseline', choices=('disabled', 'global'), default='disabled')
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    source = args.input.resolve(strict=True)
    root = repo / 'out/motion-ab' / uuid.uuid4().hex
    root.mkdir(parents=True)
    with source.open('rb') as handle:
        digest = hashlib.file_digest(handle, 'sha256').hexdigest()
    original = pipeline.depth_refresh_reason
    def baseline(frame, inferred, index, policy, cut):
        if args.baseline == 'global':
            return original(frame, inferred, index, replace(policy, local_motion_window=0), cut)
        return without_motion(frame, inferred, index, policy, cut)
    records = []
    with patch('depthsbs_app.resources.bundle_root', return_value=repo / 'out/release/DepthSBS/_internal'):
        for index, (kind, enabled) in enumerate((('warmup', False), ('warmup', True),
                ('measured', False), ('measured', True), ('measured', True), ('measured', False))):
            label = f'{index}-{kind}-' + ('on' if enabled else 'off')
            print('START ' + label, flush=True)
            with (root / f'{label}.jsonl').open('w', encoding='utf-8') as log:
                def progress(event):
                    log.write(json.dumps(event) + '\n')
                    log.flush()
                with patch.object(pipeline, 'depth_refresh_reason', original if enabled else baseline):
                    result = pipeline.convert_video(source, root / f'{label}.mp4', 'performance', progress)
            records.append(dict(kind=kind, enabled=enabled, output=str(root / f'{label}.mp4'), result=result))
    aggregate = {}
    for enabled in (False, True):
        values = [r['result'] for r in records if r['kind'] == 'measured' and r['enabled'] == enabled]
        aggregate['on' if enabled else 'off'] = dict(
            elapsed_median=statistics.median(r['elapsed_seconds'] for r in values),
            fps_median=statistics.median(r['processing_fps'] for r in values),
            inference_counts=[r['telemetry']['resources']['cuda_counters']['completed_inferences'] for r in values])
    report = dict(input=str(source), input_sha256=digest, baseline=args.baseline,
        commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip(),
        source_dirty=bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=repo)),
        package=json.loads((repo / 'out/release/DepthSBS/build-manifest.json').read_text(encoding='utf-8-sig')),
        scope='Development pipeline with bundled assets; two measured runs per variant',
        synthetic=synthetic_results(), aggregate=aggregate, runs=records)
    (root / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(aggregate), flush=True)
    print(root / 'report.json', flush=True)


if __name__ == '__main__':
    main()
