"""Read-only package selection; outputs isolated comparison artifacts."""
import json
import os
from pathlib import Path
import subprocess
import uuid
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--input', type=Path, required=True)
parser.add_argument('--old-normal-only', action='store_true')
args = parser.parse_args()

repo = Path(__file__).resolve().parents[1]
root = repo / 'out/package-environment' / uuid.uuid4().hex
root.mkdir(parents=True)
source = args.input.resolve()
report = []
cases = [('old-cpu', False)] if args.old_normal_only else [('old-cpu', True), ('new-cpu', False)]
for variant, isolated in cases:
    package = repo / ('out/release/ScreenTo3D' if variant == 'old-cpu' else 'out/gpu-preview/ScreenTo3D-GPU-Preview')
    exe = package / ('ScreenTo3D.exe' if variant == 'old-cpu' else 'ScreenTo3D-GPU-Preview.exe')
    env = os.environ.copy()
    if isolated:
        windows = os.environ['SystemRoot']
        env['PATH'] = str(Path(windows) / 'System32') + os.pathsep + windows
        env.pop('PYTHONPATH', None)
        env.pop('PYTHONHOME', None)
    output, status = root / f'{variant}.mp4', root / f'{variant}.jsonl'
    command = [str(exe), '--worker', '--input', str(source), '--output', str(output),
               '--mode', 'performance', '--status-file', str(status)]
    if variant == 'new-cpu':
        command += ['--reference-cpu', '--frame-hashes']
    subprocess.run(command, env=env, check=True, timeout=180)
    decoded = subprocess.check_output([str(package / '_internal/ffmpeg/ffmpeg.exe'), '-v', 'error',
        '-i', str(output), '-map', '0:v:0', '-pix_fmt', 'rgb24', '-f', 'hash', '-hash', 'sha256', '-'], text=True)
    completion = next(e for e in map(json.loads, status.read_text(encoding='utf-8').splitlines()) if e['event'] == 'complete')
    report.append(dict(variant=variant, isolated=isolated, decoded_hash=decoded.strip(), completion=completion))
    print(variant, decoded.strip(), flush=True)
(root / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(root / 'report.json')
