"""Opt-in real GPU/FFmpeg repeated lifecycle smoke; not part of unit discovery."""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from depthsbs_app import pipeline
from depthsbs_app.trt_backend import DepthEngine, _cuda, cudart


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--runs', type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.runs <= 20:
        parser.error('runs must be between 1 and 20')
    root = Path(__file__).resolve().parents[1] / 'out' / 'cleanup'
    root.mkdir(parents=True, exist_ok=True)
    run_dir = args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix='repeat-', dir=root))
    if args.output: run_dir.mkdir(parents=True, exist_ok=False)
    bad_input = run_dir / 'invalid.mp4'
    bad_input.write_bytes(b'not a video')
    original_popen = subprocess.Popen
    observations = []
    for iteration in range(args.runs):
        for scenario in ('success', 'cancel', 'inference_error', 'invalid_input'):
            output = run_dir / f'{iteration}-{scenario}.mp4'
            cancel = run_dir / 'cancel.token'
            sentinel = b'previous output must survive a failed job'
            if scenario != 'success':
                output.write_bytes(sentinel)
            children = []
            events = []

            def popen(*arguments, **kwargs):
                process = original_popen(*arguments, **kwargs)
                children.append(process)
                return process

            def progress(event):
                events.append(event)
                if scenario == 'cancel' and event.get('event') == 'progress':
                    cancel.touch()

            caught = None
            with patch.object(pipeline.subprocess, 'Popen', side_effect=popen):
                try:
                    if scenario == 'inference_error':
                        with patch.object(DepthEngine, 'infer', side_effect=RuntimeError('injected inference failure')):
                            pipeline.convert_video(args.input, output, 'performance', progress, cancel)
                    else:
                        source = bad_input if scenario == 'invalid_input' else args.input
                        pipeline.convert_video(source, output, 'performance', progress, cancel)
                except (RuntimeError, InterruptedError) as error:
                    caught = error
            if scenario == 'success':
                assert caught is None and events[-1]['event'] == 'complete'
                assert output.is_file()
            else:
                assert caught is not None, f'{scenario} unexpectedly succeeded'
                assert not getattr(caught, '__notes__', []), repr(caught.__notes__)
                assert output.read_bytes() == sentinel
                assert not any(event['event'] == 'complete' for event in events)
                if scenario == 'cancel':
                    assert isinstance(caught, InterruptedError)
                    assert events[-1]['event'] == 'cancelled'
                if scenario == 'inference_error':
                    assert str(caught) == 'injected inference failure'
            assert not cancel.exists()
            assert not output.with_suffix('.mp4.partial.mp4').exists()
            assert not output.with_suffix('.mp4.video-only.mp4').exists()
            assert not list(output.parent.glob(f'.{output.name}.*.mp4'))
            for child in children:
                assert child.poll() is not None, f'child {child.pid} still running'
                for stream in (child.stdin, child.stdout, child.stderr):
                    assert stream is None or stream.closed
            free, total = _cuda(cudart.cudaMemGetInfo())
            observation = dict(iteration=iteration, scenario=scenario, passed=True,
                               device_global_used_bytes=int(total - free), children=len(children))
            observations.append(observation)
            print(json.dumps(observation), flush=True)
    artifact = run_dir / 'result.json'
    artifact.write_text(json.dumps({'status': 'passed', 'observations': observations,
        'scope': 'same-process GPU lifecycle; inference failure injected, not actual device loss',
        'leak_verdict': 'not established by sampled global VRAM'}, indent=2), encoding='utf-8')
    print(artifact)


if __name__ == '__main__':
    # Exercise current source with the same model/FFmpeg assets as the package.
    assets = Path(__file__).resolve().parents[1] / 'out/release/DepthSBS/_internal'
    if not (assets / 'models/da2-small/model_fp16.onnx').is_file():
        raise RuntimeError('Build the portable package assets first')
    with patch('depthsbs_app.resources.bundle_root', return_value=assets):
        main()
