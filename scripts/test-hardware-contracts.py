"""Explicit local GPU/Qt contracts. Not run automatically on pull requests."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--group', choices=['all', 'runtime', 'projection', 'transport', 'qt', 'media', 'jobs'], default='all')
    parser.add_argument('--runtime-dir', type=Path)
    parser.add_argument('--fault-fixture', type=Path)
    parser.add_argument('--input', type=Path, help='Short declared fixture for jobs-only checks')
    args = parser.parse_args()
    if args.group in ('all', 'projection') and not args.fault_fixture:
        parser.error('projection requires --fault-fixture from build-cuda-projection-spike.ps1 -OutputDirectory')
    if args.group == 'jobs' and not args.input:
        parser.error('jobs-only requires a short fixture via --input')
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    paths = [ROOT / 'v1', ROOT, ROOT/'out/gui-python-deps', ROOT/'out/capture-python-deps', ROOT/'out/v1-python-deps']
    environment['PYTHONPATH'] = os.pathsep.join(str(p) for p in paths if p.exists())
    if args.runtime_dir:
        environment['PATH'] = str(args.runtime_dir.resolve()) + os.pathsep + environment.get('PATH', '')
    bundle = ROOT/'out/gpu-preview/ScreenTo3D-GPU-Preview/_internal'
    definitions = {
        'runtime': [('runtime', 'scripts/test-contracts.py', '--group', 'runtime', '--resource-root', str(bundle), '--report', str(args.output/'runtime.json'))],
        'projection': [('projection', 'v1/test_gpu_contracts.py', '--fault-fixture', str(args.fault_fixture.resolve()) if args.fault_fixture else '', '--output', str(args.output/'projection'))],
        'transport': [('transport', 'v1/test_texture_pool_transport.py', '--output', str(args.output/'transport'))],
        'qt': [('qt', 'v1/test_native_dual_window.py', '--output', str(args.output/'qt')),
               ('qt-lease', 'v1/test_native_dual_window.py', '--lease-error', '--output', str(args.output/'qt-lease'))],
        'media': [('media', 'v1/test_media_contracts.py', '--encoder', 'nvenc', '--media-tools', str(bundle/'ffmpeg'), '--output', str(args.output/'media'))],
    }
    definitions['jobs'] = [('jobs', 'v1/test_cuda_job_cleanup.py', '--input', str(args.input.resolve() if args.input else args.output/'media/source-h264.mp4'), '--output', str(args.output/'jobs'))]
    selected = list(definitions) if args.group == 'all' else [args.group]
    report = dict(status='failed', cases=[], scope='Named bounded hardware checks only; no throughput, long-soak or physical VR acceptance')
    try:
        for group in selected:
            for name, script, *options in definitions[group]:
                command = [sys.executable, str(ROOT/script), *options]
                started = time.monotonic()
                with (args.output/(name+'.log')).open('w', encoding='utf-8') as log:
                    process = subprocess.Popen(command, cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT,
                                               creationflags=subprocess.CREATE_NO_WINDOW)
                    try:
                        code = process.wait(timeout=120)
                    except subprocess.TimeoutExpired:
                        # The PID still belongs to our live child; terminate only its tree.
                        if process.poll() is None:
                            subprocess.run(['taskkill', '/pid', str(process.pid), '/t', '/f'], capture_output=True, timeout=15,
                                           creationflags=subprocess.CREATE_NO_WINDOW)
                        process.wait(timeout=15)
                        code = -1
                result_path = args.output/('runtime.json' if name == 'runtime' else name+'/report.json')
                recorded = json.loads(result_path.read_text()) if result_path.is_file() else {}
                passed = code == 0 and (recorded.get('status') == 'passed' or recorded.get('passed') is True)
                report['cases'].append(dict(name=name, status='passed' if passed else 'failed', exit_code=code,
                                            elapsed_seconds=time.monotonic()-started, result=str(result_path)))
                print(name + ': ' + ('passed' if passed else 'failed'), flush=True)
        report['status'] = 'passed' if report['cases'] and all(c['status'] == 'passed' for c in report['cases']) else 'failed'
    finally:
        (args.output/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
