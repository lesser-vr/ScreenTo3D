"""Real CUDA, default-size sequence and failure-path checks; isolated env only."""
import argparse
import gc
import json
from pathlib import Path
import subprocess
import uuid
from unittest.mock import patch

import cv2
import numpy as np
import torch

from screento3d_app import pipeline
from screento3d_app.depth_backend import BackendBinding
from vda_streaming_experiment import ROOT, VdaStreamingEngine, binding


def cache_bytes(model):
    storages = {}
    for entry in model.frame_cache_list:
        for tensor in entry:
            storage = tensor.untyped_storage()
            storages[storage.data_ptr()] = storage.nbytes()
    return sum(storages.values())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    args = parser.parse_args()
    root = ROOT / 'out/vda-lifecycle' / uuid.uuid4().hex
    root.mkdir(parents=True)
    report = dict(passed=False, input=str(args.input), input_size=518,
                  gpu=torch.cuda.get_device_name(), torch=torch.__version__, samples=[], jobs=[])
    try:
        baseline = torch.cuda.memory_allocated()
        capture = cv2.VideoCapture(str(args.input))
        try:
            with VdaStreamingEngine() as engine:
                count = 0
                while True:
                    ok, bgr = capture.read()
                    if not ok:
                        break
                    depth = engine.infer(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
                    assert depth.shape == (1, *bgr.shape[:2]) and np.isfinite(depth).all()
                    count += 1
                    if count % 10 == 0:
                        report['samples'].append(engine.telemetry())
                        report['samples'][-1]['unique_cache_bytes'] = cache_bytes(engine.model)
                assert count >= 64, 'Need at least 64 real frames'
                report['sequence'] = engine.telemetry()
                assert report['sequence']['cache_entries'] == 42
        finally:
            capture.release()
        gc.collect()
        torch.cuda.synchronize()
        report['after_close_allocated'] = torch.cuda.memory_allocated()
        report['baseline_allocated'] = baseline
        # Diagnostic only: distinguish process-owned cuBLAS workspaces from
        # live model tensors. Never use this private API in the application.
        torch._C._cuda_clearCublasWorkspaces()
        report['after_workspace_clear_allocated'] = torch.cuda.memory_allocated()
        assert report['after_workspace_clear_allocated'] == baseline
        steady = [s['cuda_allocated_bytes'] for s in report['samples'][4:]]
        report['steady_allocated_span'] = max(steady) - min(steady)
        # Allocator totals can vary; gate the actual unique cache storage after
        # duplicated first-frame entries have left the sliding window.
        assert len({s['unique_cache_bytes'] for s in report['samples'][4:]}) == 1
        print(f'PASS: {count} original-size frames, cache and allocated-memory checks', flush=True)

        assets = ROOT / 'out/gpu-preview/ScreenTo3D-GPU-Preview/_internal'
        with patch('screento3d_app.resources.bundle_root', return_value=assets):
            for kind in ('cancel', 'inference_failure', 'success'):
                job = root / kind
                job.mkdir()
                output = job / 'output.mp4'
                output.write_bytes(b'existing-output-sentinel')
                cancel = job / 'cancel.flag'
                engines, processes = [], []
                spec = binding()

                def factory(progress):
                    current = VdaStreamingEngine()
                    engines.append(current)
                    if kind == 'inference_failure':
                        original = current.model.infer_video_depth_one

                        def fail(*a, **kw):
                            if current.calls == 1:
                                raise RuntimeError('injected VDA inference failure')
                            return original(*a, **kw)
                        current.model.infer_video_depth_one = fail
                    return current

                def progress(event):
                    if kind == 'cancel' and event['event'] == 'progress':
                        cancel.touch()

                original_popen = subprocess.Popen

                def track(*a, **kw):
                    process = original_popen(*a, **kw)
                    processes.append(process)
                    return process

                completion = None
                try:
                    with patch('subprocess.Popen', side_effect=track):
                        completion = pipeline.convert_video(args.input, output, 'video-quality', progress,
                            cancel, depth_backend=BackendBinding(spec.spec, factory, spec.prepare))
                except InterruptedError:
                    assert kind == 'cancel'
                except RuntimeError as error:
                    assert kind == 'inference_failure' and str(error) == 'injected VDA inference failure'
                else:
                    assert kind == 'success'
                assert len(engines) == 1 and engines[0].closed and engines[0].model is None
                assert all(p.poll() is not None for p in processes)
                assert sorted(p.name for p in job.iterdir()) == ['output.mp4']
                if kind != 'success':
                    assert output.read_bytes() == b'existing-output-sentinel'
                else:
                    assert completion['frames'] == count
                    check = cv2.VideoCapture(str(output))
                    try:
                        decoded = 0
                        while check.read()[0]:
                            decoded += 1
                        assert decoded == count
                    finally:
                        check.release()
                report['jobs'].append(dict(kind=kind, passed=True, completion=completion))
                print(f'PASS: {kind}', flush=True)
        report['passed'] = True
    finally:
        (root / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(root / 'report.json', flush=True)


if __name__ == '__main__':
    main()
