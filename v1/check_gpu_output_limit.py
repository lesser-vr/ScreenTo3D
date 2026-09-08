"""Packaged unsupported-width rejection must preserve prior output."""
import argparse
import json
from pathlib import Path
import subprocess
import uuid


def check(source):
    repo = Path(__file__).resolve().parents[1]
    root = repo / 'out/gpu-output-limit' / uuid.uuid4().hex
    root.mkdir(parents=True)
    output, status = root / 'output.mp4', root / 'events.jsonl'
    sentinel = b'prior-output-must-survive'
    output.write_bytes(sentinel)
    exe = repo / 'out/gpu-preview/DepthSBS-GPU-Preview/DepthSBS-GPU-Preview.exe'
    process = subprocess.run([str(exe), '--worker', '--input', str(source.resolve()),
        '--output', str(output), '--status-file', str(status)], timeout=30)
    events = list(map(json.loads, status.read_text(encoding='utf-8').splitlines()))
    errors = [e for e in events if e['event'] == 'error']
    assert process.returncode == 1 and len(errors) == 1
    assert errors[0]['type'] == 'ValueError' and (errors[0].get('code') == 'output_geometry' or '4096' in errors[0]['message'])
    assert not any(e['event'] in ('start', 'progress', 'complete') for e in events)
    assert output.read_bytes() == sentinel
    assert not Path(str(output) + '.partial.mp4').exists()
    assert not Path(str(output) + '.video-only.mp4').exists()
    assert not list(output.parent.glob(f'.{output.name}.*.mp4'))
    report = root / 'report.json'
    report.write_text(json.dumps(dict(passed=True, scope='unsupported-width rejection, not 4K conversion',
        input=str(source), error=errors[0], prior_output_preserved=True), indent=2), encoding='utf-8')
    print(report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    check(parser.parse_args().input)
