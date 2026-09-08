"""Explicit real-GPU job cleanup with injected errors; not device-loss simulation."""
import argparse
import json
from pathlib import Path
import subprocess
from unittest.mock import patch
import uuid
from cuda_projection_experiment import CudaProjection
from depthsbs_app import pipeline
from depthsbs_app.local_projection import checked_dll
from depthsbs_app.trt_backend import DepthEngine, _cuda, cudart


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    root = args.output.resolve() if args.output else repo / 'out/cuda-job-cleanup' / uuid.uuid4().hex
    root.mkdir(parents=True)
    observations = []
    original_popen = subprocess.Popen
    original_infer = DepthEngine.infer
    with patch('depthsbs_app.resources.bundle_root', return_value=repo / 'out/release/DepthSBS/_internal'):
        for cycle in range(3):
            for scenario in ('success', 'cancel', 'projection_error', 'inference_error', 'create_error', 'close_error'):
                output = root / f'{cycle}-{scenario}.mp4'
                sentinel = b'previous output must survive'
                output.write_bytes(sentinel)
                cancel = root / 'cancel.token'
                owners, children, events = [], [], []
                inference_calls = 0
                class Owner(CudaProjection):
                    def project(self, *a, **kw):
                        if scenario == 'projection_error' and self.calls == 2:
                            with patch.object(self.dll, 'projection_run', return_value=17):
                                return super().project(*a, **kw)
                        return super().project(*a, **kw)
                    def close(self):
                        was_open = bool(self.handle.value)
                        super().close()
                        if scenario == 'close_error' and was_open:
                            raise RuntimeError('injected GPU close failure')
                def factory(width, height):
                    if scenario == 'create_error':
                        raise RuntimeError('injected GPU create failure')
                    owner = Owner(width, height, dll_path=checked_dll())
                    owners.append(owner)
                    return owner
                def popen(*a, **kw):
                    child = original_popen(*a, **kw)
                    children.append(child)
                    return child
                def infer(engine, tensor):
                    nonlocal inference_calls
                    inference_calls += 1
                    if scenario == 'inference_error' and inference_calls == 3:
                        raise RuntimeError('injected depth inference failure')
                    return original_infer(engine, tensor)
                def progress(event):
                    events.append(event)
                    if scenario == 'cancel' and event['event'] == 'progress':
                        cancel.touch()
                caught = None
                with patch.object(pipeline.subprocess, 'Popen', side_effect=popen), patch.object(DepthEngine, 'infer', infer):
                    try:
                        pipeline.convert_video(args.input, output, 'performance', progress, cancel,
                                               projection_factory=factory)
                    except (RuntimeError, InterruptedError) as error:
                        caught = error
                if scenario == 'success':
                    assert caught is None and events[-1]['event'] == 'complete'
                    assert output.read_bytes() != sentinel
                    assert events[-1]['telemetry']['stereo']['algorithm'] == Owner.algorithm
                else:
                    assert caught is not None
                    assert not any(e['event'] == 'complete' for e in events)
                    assert output.read_bytes() == sentinel
                    if scenario == 'cancel':
                        assert isinstance(caught, InterruptedError)
                        assert events[-1]['event'] == 'cancelled'
                assert all(not owner.handle.value for owner in owners)
                assert not cancel.exists()
                assert not output.with_suffix('.mp4.partial.mp4').exists()
                assert not output.with_suffix('.mp4.video-only.mp4').exists()
                assert not list(output.parent.glob(f'.{output.name}.*.mp4'))
                for child in children:
                    assert child.poll() is not None
                    assert all(s is None or s.closed for s in (child.stdin, child.stdout, child.stderr))
                free, total = _cuda(cudart.cudaMemGetInfo())
                row = dict(cycle=cycle, scenario=scenario, passed=True,
                    gpu_eye_calls=sum(o.calls for o in owners), device_global_used_bytes=int(total-free))
                observations.append(row)
                print(json.dumps(row), flush=True)
    (root / 'report.json').write_text(json.dumps(dict(status='passed', observations=observations,
        scope='Injected errors after actual GPU use; close error injected after real free; not device loss'), indent=2), encoding='utf-8')
    print(root / 'report.json')


if __name__ == '__main__':
    main()
