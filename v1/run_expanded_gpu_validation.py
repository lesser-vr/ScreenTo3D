"""Sequential workload matrix; never overlap GPU timing jobs."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import uuid

from validate_packaged_comparison import validate
from check_gpu_output_limit import check as check_output_limit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    root = repo / 'out/expanded-gpu-validation' / uuid.uuid4().hex
    root.mkdir(parents=True)
    report = {'cases': [], 'passed': False}

    def execute(command, name):
        print('START ' + name, flush=True)
        log = root / f'{name}.log'
        with log.open('w', encoding='utf-8') as stream:
            result = subprocess.run(command, cwd=repo, stdout=stream, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError(f'{name} failed: {log}')
        return log.read_text(encoding='utf-8').strip().splitlines()[-1]

    def compare(source, mode, name, diagnostic=False):
        command = [sys.executable, str(repo / 'v1/compare_packaged_renderers.py'),
                   '--input', str(source), '--mode', mode]
        if diagnostic:
            command.append('--diagnostics-only')
        path = Path(execute(command, name))
        validate(source, path)
        result = json.loads(path.read_text(encoding='utf-8'))
        report['cases'].append(dict(name=name, report=str(path), aggregate=result.get('aggregate'), passed=True))
        print('PASS ' + name + ' ' + json.dumps(result.get('aggregate')), flush=True)

    try:
        for mode in ('balanced', 'video-quality', 'offline-quality'):
            compare(args.input.resolve(), mode, mode)
        ffmpeg = repo / 'out/gpu-preview/DepthSBS-GPU-Preview/_internal/ffmpeg/ffmpeg.exe'
        for width, height in ((1920, 1080), (3840, 2160)):
            source = root / f'synthetic-{width}x{height}.mp4'
            command = [str(ffmpeg), '-n', '-v', 'error', '-f', 'lavfi', '-i',
                f'testsrc2=size={width}x{height}:rate=30', '-f', 'lavfi', '-i',
                'sine=frequency=440:sample_rate=48000', '-t', '1', '-c:v', 'h264_nvenc',
                '-preset', 'p1', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(source)]
            subprocess.run(command, check=True, timeout=120)
            report['cases'].append(dict(name=f'fixture-{width}', command=command))
            if width == 3840:
                path = check_output_limit(source)
                report['cases'].append(dict(name='4k-rejection-not-conversion', report=str(path), passed=True))
            else:
                compare(source, 'performance', f'resolution-{width}', diagnostic=True)
        source = repo / 'out/media-smoke/soak-cfr-720p30-300s.mp4'
        path = execute(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
            str(repo / 'scripts/soak-v1.ps1'), '-SourcePath', str(source), '-GpuPreview',
            '-TimeoutSeconds', '1200'], 'gpu-soak-300s')
        report['cases'].append(dict(name='gpu-soak-300s', report=path, passed=True))
        print('PASS gpu-soak-300s ' + path, flush=True)
        report['passed'] = True
    finally:
        (root / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(root / 'report.json', flush=True)


if __name__ == '__main__':
    main()
