"""Bounded source-app file conversion on both installed Base FP16 profiles."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

import cv2

from screento3d_app.desktop_jobs import ROOT, BUNDLE
from public_test_media import CORPUS, prepare


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    prepare()
    report = dict(passed=False, runs=[])
    ffmpeg = BUNDLE / 'ffmpeg/ffmpeg.exe'
    try:
        for width, height, shape, codec in ((1056, 608, [1, 3, 518, 896], 'h264'), (1280, 720, [1, 3, 518, 924], 'hevc')):
            source, target = args.output / f'{width}-input.mp4', args.output / f'{width}-sbs.mp4'
            subprocess.run([str(ffmpeg), '-v', 'error', '-i', str(CORPUS / 'FloorballGame.mp4'),
                '-frames:v', '8', '-vf', f'scale={width}:{height}', '-an', str(source)], check=True, creationflags=subprocess.CREATE_NO_WINDOW)
            result = subprocess.run([sys.executable, '-m', 'screento3d_app.main', '--worker',
                '--input', str(source), '--output', str(target), '--mode', 'balanced', '--depth-backend', 'da2-base',
                '--da2-base-engine-dir', str(ROOT / 'out/da2-base-local'), '--runtime-dir', 'C:/TensorRT/TensorRT-11.2.1.2/bin',
                '--media-tools', str(BUNDLE / 'ffmpeg'), '--output-codec', codec], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            (args.output / f'{width}.log').write_text(result.stdout + '\n' + result.stderr, encoding='utf-8')
            result.check_returncode()
            events = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
            backend = next(e for e in events if e['event'] == 'depth_backend')
            completed = next(e for e in events if e['event'] == 'complete')
            resources = completed['telemetry']['resources']
            assert backend['runtime'] == resources['runtime'] == 'tensorrt-fp16'
            assert resources['input_shape'] == shape and resources['io_precision'] == 'fp32'
            assert completed['frames'] == 8
            capture = cv2.VideoCapture(str(target))
            decoded = 0
            try:
                while True:
                    ok, frame = capture.read()
                    if not ok:
                        break
                    assert frame.shape == (height, width * 2, 3)
                    decoded += 1
            finally:
                capture.release()
            assert decoded == 8
            report['runs'].append(dict(size=[width, height], decoded=decoded, codec=codec, resources=resources))
            print(f'PASS {width}x{height}: {resources["runtime"]}', flush=True)
        report['passed'] = True
    finally:
        (args.output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
