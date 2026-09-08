"""Same executable, explicit renderer, separate hash diagnostics and timings."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import time
import uuid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--mode', default='performance')
    parser.add_argument('--output-codec', choices=('h264', 'hevc'), default='h264')
    parser.add_argument('--diagnostics-only', action='store_true')
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    package = repo / 'out/gpu-preview/DepthSBS-GPU-Preview'
    exe = package / 'DepthSBS-GPU-Preview.exe'
    root = repo / 'out/packaged-comparison' / uuid.uuid4().hex
    root.mkdir(parents=True)
    env = os.environ.copy()
    windows = os.environ['SystemRoot']
    env['PATH'] = str(Path(windows) / 'System32') + os.pathsep + windows
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    def digest(path):
        with path.open('rb') as stream:
            return hashlib.file_digest(stream, 'sha256').hexdigest()
    report = dict(mode=args.mode, output_codec=args.output_codec, input_sha256=digest(args.input),
        executable_sha256=digest(exe), os=platform.platform(),
        package=json.loads((package / 'build-manifest.json').read_text(encoding='utf-8-sig')),
        projection=json.loads((package / 'projection-build-manifest.json').read_text(encoding='utf-8-sig')),
        gpu=subprocess.check_output(['nvidia-smi', '--query-gpu=name,driver_version,compute_cap', '--format=csv,noheader'], text=True).strip(),
        commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip(),
        dirty=bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=repo)),
        runs=[], passed=False)
    ffmpeg = package / '_internal/ffmpeg/ffmpeg.exe'

    def run(variant, kind, index):
        stem = f'{kind}-{index}-{variant}'
        status, output = root / f'{stem}.jsonl', root / f'{stem}.mp4'
        command = [str(exe), '--worker', '--input', str(args.input.resolve()), '--output', str(output),
                   '--mode', args.mode, '--status-file', str(status), '--output-codec', args.output_codec]
        if variant == 'cpu':
            command.append('--reference-cpu')
        if kind == 'diagnostic':
            command.append('--frame-hashes')
        start = time.perf_counter()
        subprocess.run(command, env=env, check=True, timeout=240)
        wall = time.perf_counter() - start
        completion = next(e for e in (json.loads(line) for line in status.read_text(encoding='utf-8').splitlines()) if e['event'] == 'complete')
        telemetry = completion['telemetry']
        expected = 'forward_zbuffer_cpu' if variant == 'cpu' else 'forward_zbuffer_cuda_preview'
        assert telemetry['stereo']['algorithm'] == expected
        assert bool(telemetry['diagnostic_hashes']) == (kind == 'diagnostic')
        if variant == 'gpu':
            assert telemetry['stereo']['projection_resources']['completed_eye_calls'] == completion['frames'] * 2
        decoded_hash = subprocess.check_output([str(ffmpeg), '-v', 'error', '-i', str(output),
            '-map', '0:v:0', '-pix_fmt', 'rgb24', '-f', 'hash', '-hash', 'sha256', '-'], env=env, text=True).strip()
        result = dict(variant=variant, kind=kind, index=index, process_wall_seconds=wall,
                      decoded_hash=decoded_hash, completion=completion)
        report['runs'].append(result)
        (root / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(f'{kind} {index} {variant}: {wall:.3f}s hashes={telemetry["diagnostic_hashes"]}', flush=True)

    try:
        for index in range(2):
            for variant in ('cpu', 'gpu') if index % 2 == 0 else ('gpu', 'cpu'):
                run(variant, 'diagnostic', index)
        if not args.diagnostics_only:
            for variant in ('cpu', 'gpu'):
                run(variant, 'warmup', 0)
            for index in range(5):
                for variant in ('cpu', 'gpu') if index % 2 == 0 else ('gpu', 'cpu'):
                    run(variant, 'measured', index)
            report['aggregate'] = {}
            for variant in ('cpu', 'gpu'):
                samples = [r for r in report['runs'] if r['variant'] == variant and r['kind'] == 'measured']
                report['aggregate'][variant] = {
                    field: dict(median=statistics.median(values), minimum=min(values), maximum=max(values))
                    for field, values in (
                        ('process_wall_seconds', [r['process_wall_seconds'] for r in samples]),
                        ('processing_fps', [r['completion']['processing_fps'] for r in samples]))}
        report['passed'] = True
    finally:
        (root / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(root / 'report.json', flush=True)


if __name__ == '__main__':
    main()
