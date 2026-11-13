"""Development-only matched VDA EMA comparison and tensor-boundary inventory."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import uuid
from unittest.mock import patch

import cv2
import numpy as np

from screento3d_app import pipeline
from screento3d_app.config import MODES
from screento3d_app.depth_backend import BackendBinding
from vda_streaming_experiment import ROOT, VdaStreamingEngine, binding


def describe(value):
    if isinstance(value, (list, tuple)):
        return [describe(item) for item in value]
    if hasattr(value, 'shape'):
        return dict(shape=list(value.shape), dtype=str(value.dtype), device=str(value.device))
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    args = parser.parse_args()
    root = ROOT / 'out/vda-temporal-comparison' / uuid.uuid4().hex
    root.mkdir(parents=True)
    report = dict(passed=False, input=str(args.input), runs={}, boundary=[])
    policy = MODES['video-quality']
    try:
        with patch('screento3d_app.resources.bundle_root', return_value=ROOT / 'out/gpu-preview/ScreenTo3D-GPU-Preview/_internal'):
            for name, alpha in [('existing_ema', policy.temporal_alpha), ('native_only', 1.0)]:
                def factory(progress):
                    engine = VdaStreamingEngine()
                    original = engine.model.forward_depth
                    def forward(features, shape, cached_hidden_state_list=None):
                        result = original(features, shape, cached_hidden_state_list)
                        if name == 'existing_ema' and len(report['boundary']) < 2:
                            report['boundary'].append(dict(features=describe(features), input_shape=list(shape),
                                cache_input=describe(cached_hidden_state_list), output=describe(result)))
                        return result
                    engine.model.forward_depth = forward
                    return engine
                spec = binding()
                with patch.dict(MODES, {'video-quality': replace(policy, temporal_alpha=alpha)}):
                    report['runs'][name] = pipeline.convert_video(args.input, root / f'{name}.mp4',
                        'video-quality', lambda event: None, diagnostic_hashes=True,
                        depth_backend=BackendBinding(spec.spec, factory, spec.prepare))
                print('PASS: ' + name, flush=True)
        a, b = report['runs'].values()
        assert a['frames'] == b['frames']
        assert a['telemetry']['diagnostic_hashes']['depth'] == b['telemetry']['diagnostic_hashes']['depth']
        captures = [cv2.VideoCapture(str(p)) for p in (args.input, root / 'existing_ema.mp4', root / 'native_only.mp4')]
        try:
            for index in (20, 40, 60, 80, 100):
                rows = []
                for label, capture in zip(('SOURCE', 'VDA existing EMA - left eye', 'VDA native only - left eye'), captures):
                    capture.set(cv2.CAP_PROP_POS_FRAMES, index)
                    ok, frame = capture.read()
                    if not ok:
                        raise RuntimeError('Missing comparison frame')
                    if label != 'SOURCE':
                        frame = frame[:, :frame.shape[1] // 2]
                    frame = frame.copy()
                    cv2.putText(frame, label, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, .8, (0, 0, 255), 2)
                    rows.append(frame)
                cv2.imwrite(str(root / f'frame-{index}.png'), np.concatenate(rows, axis=0))
        finally:
            for capture in captures:
                capture.release()
        report['passed'] = True
    finally:
        (root / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(root / 'report.json', flush=True)


if __name__ == '__main__':
    main()
