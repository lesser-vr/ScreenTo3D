"""Explicit real-GPU checks; run only in the separate VDA environment."""
import argparse
import gc
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid
from unittest.mock import patch

import cv2
import numpy as np
import torch

from vda_streaming_experiment import VdaStreamingEngine, upstream_class, checked_weights, binding, ROOT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    args = parser.parse_args()
    root = ROOT / 'out/vda-oracle-checks' / uuid.uuid4().hex
    root.mkdir(parents=True)
    report = dict(passed=False, checks=[], torch=torch.__version__, cuda=torch.version.cuda,
        gpu=torch.cuda.get_device_name(), input_size=140, scope='reduced-size CUDA contract oracle, not quality/speed acceptance',
        dependencies=subprocess.check_output([sys.executable, '-m', 'pip', 'freeze'], text=True).splitlines())
    try:
        capture = cv2.VideoCapture(str(args.input))
        try:
            ok, bgr = capture.read()
            if not ok:
                raise ValueError('Cannot read user input')
            frame = cv2.resize(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), (320, 184))
        finally:
            capture.release()
        model = upstream_class()(encoder='vits', features=64, out_channels=[48, 96, 192, 384])
        model.load_state_dict(checked_weights(), strict=True)
        model = model.cuda().eval()
        expected = []
        for index in range(6):
            expected.append(model.infer_video_depth_one(np.roll(frame, index, axis=1), input_size=140, device='cuda', fp32=False).copy())
        del model
        gc.collect()
        with VdaStreamingEngine(input_size=140) as engine:
            for index, depth in enumerate(expected):
                actual = engine.infer(np.roll(frame, index, axis=1))
                np.testing.assert_array_equal(actual[0], depth)
            report['checks'].append('six exact upstream/adapter outputs')
            immutable = actual.copy()
            for index in range(6, 64):
                engine.infer(np.roll(frame, index, axis=1))
            np.testing.assert_array_equal(actual, immutable)
            report['cache_at_64'] = engine.telemetry()
            assert report['cache_at_64']['cache_entries'] == 42
            report['checks'].append('64 frames; cache limit 42; owned output')
            engine.reset('scene_cut')
            assert not engine.model.frame_cache_list and engine.model.transform is None and engine.model.id == -1
            reset_output = engine.infer(frame)
            np.testing.assert_array_equal(reset_output[0], expected[0])
            report['checks'].append('cut reset equals fresh first frame')
            resized = cv2.resize(frame, (160, 96))
            try:
                engine.infer(resized)
            except ValueError:
                pass
            else:
                raise AssertionError('Shape change silently accepted')
            engine.reset('source_change')
            assert engine.infer(resized).shape == (1, 96, 160)
            report['checks'].append('shape change rejected until reset')
        try:
            engine.infer(frame)
        except RuntimeError:
            pass
        else:
            raise AssertionError('Closed engine accepted work')
        with VdaStreamingEngine(input_size=518) as default_engine:
            default_depth = default_engine.infer(frame)
            assert np.isfinite(default_depth).all()
            report['default_518'] = default_engine.telemetry()
            report['default_depth_sha256'] = hashlib.sha256(default_depth.tobytes()).hexdigest()
        report['checks'].append('default 518 single-frame CUDA smoke')
        print('PASS: oracle equality, cache, reset and default-size smoke', flush=True)

        from depthsbs_app import pipeline
        with patch('depthsbs_app.resources.bundle_root', return_value=ROOT / 'out/gpu-preview/DepthSBS-GPU-Preview/_internal'):
            fixture = ROOT / 'out/quality-fixtures/6a90bee5354946c39182fa459cb2f611/motion-hevc.mp4'
            with (root / 'pipeline.jsonl').open('w', encoding='utf-8') as stream:
                def progress(event):
                    stream.write(json.dumps(event) + '\n')
                    stream.flush()
                completion = pipeline.convert_video(fixture, root / 'output.mp4', 'video-quality', progress,
                                                    depth_backend=binding(input_size=140))
            assert completion['frames'] == 48
            assert completion['telemetry']['scene_cut_resets'] == 1
            assert completion['telemetry']['resources']['completed_inferences'] == 48
            assert completion['depth_backend']['model_id'] == 'vda-small-streaming-experimental'
            report['completion'] = completion
        report['checks'].append('real-model full pipeline 48 frames and one scene cut')
        report['passed'] = True
    finally:
        (root / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(root / 'report.json', flush=True)


if __name__ == '__main__':
    main()
