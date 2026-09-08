"""Packaged smoke checks, not a sustained or repeated performance benchmark."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output-codec', choices=('h264', 'hevc'), default='h264')
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    package = repo / 'out/gpu-preview/DepthSBS-GPU-Preview'
    exe = package / 'DepthSBS-GPU-Preview.exe'
    root = repo / 'out/gpu-preview-checks' / uuid.uuid4().hex
    root.mkdir(parents=True)
    env = os.environ.copy()
    windows = os.environ['SystemRoot']
    env['PATH'] = str(Path(windows) / 'System32') + os.pathsep + windows
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    report = {'scope': 'isolated PATH on development PC; one run per mode; not clean-machine certification',
              'input': str(args.input), 'runs': [], 'passed': False}

    def events(path):
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]

    def probe(path):
        raw = subprocess.check_output([str(package / '_internal/ffmpeg/ffprobe.exe'),
            '-v', 'error', '-count_frames', '-show_streams', '-of', 'json', str(path)], env=env)
        return json.loads(raw)['streams']

    source = probe(args.input)
    video = next(s for s in source if s['codec_type'] == 'video')
    try:
        diagnostic = root / 'diagnostics.jsonl'
        subprocess.run([str(exe), '--diagnostics', '--status-file', str(diagnostic)],
                       check=True, timeout=120, env=env)
        assert any(e['event'] == 'diagnostics' for e in events(diagnostic))
        for mode in ('performance', 'balanced', 'video-quality', 'offline-quality'):
            status, output = root / f'{mode}.jsonl', root / f'{mode}.mp4'
            start = time.perf_counter()
            subprocess.run([str(exe), '--worker', '--input', str(args.input), '--output', str(output),
                '--mode', mode, '--output-codec', args.output_codec, '--status-file', str(status)], check=True, timeout=180, env=env)
            elapsed = time.perf_counter() - start
            completion = next(e for e in events(status) if e['event'] == 'complete')
            assert completion['telemetry']['stereo']['algorithm'] == 'forward_zbuffer_cuda_preview'
            result = probe(output)
            converted = next(s for s in result if s['codec_type'] == 'video')
            assert converted['codec_name'] == args.output_codec
            assert converted['codec_tag_string'] == ('hvc1' if args.output_codec == 'hevc' else 'avc1')
            assert completion['output_codec'] == args.output_codec
            assert converted['width'] == video['width'] * 2 and converted['height'] == video['height']
            assert converted['nb_read_frames'] == video['nb_read_frames']
            assert converted['avg_frame_rate'] == video['avg_frame_rate']
            assert abs(float(converted['duration']) - float(video['duration'])) < 0.05
            assert any(s['codec_type'] == 'audio' for s in result) == any(s['codec_type'] == 'audio' for s in source)
            report['runs'].append({'mode': mode, 'process_wall_seconds': elapsed, 'completion': completion})
            print(f'PASS {mode}: {elapsed:.3f}s', flush=True)

        output, status, cancel = root / 'cancel.mp4', root / 'cancel.jsonl', root / 'cancel.token'
        output.write_bytes(b'previous-output-sentinel')
        sentinel = hashlib.sha256(output.read_bytes()).hexdigest()
        process = subprocess.Popen([str(exe), '--worker', '--input', str(args.input), '--output', str(output),
            '--mode', 'balanced', '--output-codec', args.output_codec, '--status-file', str(status), '--cancel-file', str(cancel)], env=env)
        deadline = time.monotonic() + 60
        requested = False
        try:
            while process.poll() is None:
                if time.monotonic() > deadline:
                    raise TimeoutError('Packaged cancel timed out')
                # Only parse complete JSONL lines while the worker is writing.
                if not requested and status.exists() and '"event": "progress"' in status.read_text(encoding='utf-8'):
                    cancel.touch()
                    requested = True
                time.sleep(0.02)
            assert requested and process.returncode == 2
        finally:
            if process.poll() is None:
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], env=env, check=True)
                process.wait(timeout=10)
        assert hashlib.sha256(output.read_bytes()).hexdigest() == sentinel
        assert not cancel.exists()
        assert not Path(str(output) + '.partial.mp4').exists()
        assert not Path(str(output) + '.video-only.mp4').exists()
        assert not list(output.parent.glob(f'.{output.name}.*.mp4'))
        assert any(e['event'] == 'cancelled' for e in events(status))
        assert not any(e['event'] == 'complete' for e in events(status))
        report['cancel_preserved_output'] = True
        report['passed'] = True
    finally:
        (root / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(root / 'report.json', flush=True)


if __name__ == '__main__':
    main()
