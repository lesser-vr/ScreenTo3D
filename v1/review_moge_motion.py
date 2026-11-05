"""Create local, browser-compatible left-eye previews and scoped proxy summaries."""
import argparse
import html
import json
from pathlib import Path
import subprocess

import cv2
import numpy as np

from depthsbs_app.desktop_jobs import BUNDLE
from compare_small_aspect import digest


def validate_report(report):
    if report['status'] != 'measured' or not report['motion']:
        raise ValueError('Completed motion experiment required')
    count = report['frames_per_source']
    if not 5 <= count <= 360:
        raise ValueError('Invalid frame count')
    expected = {(source, model) for source in report['sources']
                for model in ('da2-trt-fp32', 'moge-fp16-1200')}
    actual = {(row['source'], row['model']) for row in report['cases']}
    if actual != expected or len(report['videos']) != len(expected):
        raise ValueError('Missing or unexpected video/model/source')
    for source, model in expected:
        indices = [r['frame'] for r in report['cases'] if r['source'] == source and r['model'] == model]
        if indices != list(range(count)):
            raise ValueError('Missing, duplicated or unordered source frames')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    directory = args.directory.resolve(strict=True)
    report = json.loads((directory/'report.json').read_text())
    validate_report(report)
    for video in report['videos']:
        if not video['decoded'] or digest(Path(video['path'])) != video['sha256']:
            raise ValueError('Video provenance mismatch')
    ffmpeg, ffprobe = BUNDLE/'ffmpeg/ffmpeg.exe', BUNDLE/'ffmpeg/ffprobe.exe'
    summary = {'scope': 'Sampled still review plus flow-aligned depth residual proxy, '
                       'not ground truth, playback observation or HMD comfort approval.',
               'models': {}, 'previews': []}
    sections = []
    for source in report['sources']:
        summary['models'][source] = {}
        for name in ('da2-trt-fp32', 'moge-fp16-1200'):
            rows = [r for r in report['cases'] if r['source'] == source and r['model'] == name]
            summary['models'][source][name] = {}
            for key in ('flow_residual_mae', 'flow_reliable_fraction', 'normalized_change_mae', 'processing_ms'):
                values = [r[key] for r in rows if key in r]
                summary['models'][source][name][key] = dict(
                    mean=float(np.mean(values)), median=float(np.median(values)),
                    p95=float(np.percentile(values, 95)), count=len(values))
        pending = directory/f'{source}-review.partial.mp4'
        final = directory/f'{source}-review.mp4'
        if pending.exists() or final.exists():
            raise FileExistsError('Review output already exists')
        subprocess.run([str(ffmpeg), '-v', 'error', '-nostdin', '-n',
            '-i', str(directory/f'{source}-da2-trt-fp32.mp4'),
            '-i', str(directory/f'{source}-moge-fp16-1200.mp4'),
            '-filter_complex', '[0:v]crop=3840:2160:0:0,scale=960:540[a];'
                               '[1:v]crop=3840:2160:0:0,scale=960:540[b];[a][b]hstack[v]',
            '-map', '[v]', '-an', '-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
            '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(pending)], check=True, timeout=180)
        stream = json.loads(subprocess.check_output([str(ffprobe), '-v', 'error', '-count_frames',
            '-select_streams', 'v:0', '-show_streams', '-of', 'json', str(pending)], timeout=120))['streams'][0]
        if (stream['width'], stream['height'], int(stream['nb_read_frames'])) != (1920, 540, report['frames_per_source']):
            raise ValueError('Review preview geometry/count mismatch')
        pending.rename(final)
        summary['previews'].append(dict(path=final.name, sha256=digest(final), stream=stream))
        samples = list(range(0, report['frames_per_source'], 60)) + [report['frames_per_source']-1]
        images = [cv2.imread(str(directory/f'{source}-{i}-eye-crops.jpg')) for i in samples]
        if any(img is None for img in images):
            raise ValueError('Missing sampled eye crop')
        if not cv2.imwrite(str(directory/f'{source}-sequence.jpg'), np.hstack(images)):
            raise RuntimeError('Sequence write failed')
        sections.append(f'<section><h2>{html.escape(source)}</h2><p>왼쪽: DA2 Small · 오른쪽: MoGe-2 Small FP16/1200</p>'
            f'<video controls loop muted preload="metadata" src="{final.name}"></video>'
            '<p>두 영상 모두 왼쪽 눈만 축소한 비교용입니다. 아래 Full SBS 원본은 눈당 3840×2160입니다.</p>'
            f'<a href="{source}-da2-trt-fp32.mp4">DA2 Full SBS</a> · '
            f'<a href="{source}-moge-fp16-1200.mp4">MoGe Full SBS</a> · '
            f'<a href="{source}-sequence.jpg">시간별 양안 원본 픽셀 크롭</a></section>')
        print(source, 'review preview verified', flush=True)
    (directory/'review-summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    page = '''<!doctype html><html lang="ko"><meta charset="utf-8"><title>MoGe Small 비교</title>
<style>body{background:#15181d;color:#e4e9f0;font:16px system-ui;max-width:1440px;margin:32px auto;padding:0 24px}
video{width:100%;background:#000}section{padding:20px;background:#21262e;margin:24px 0;border-radius:12px}
a{color:#8ebeff}p{line-height:1.6}h1{font-size:28px}</style>
<h1>DA2 Small / MoGe-2 Small — 6초 동작 비교</h1>
<p>공개 영상 3종 · 원본 60fps 유지 · 매 프레임 깊이 갱신 · 동일 입체 강도.
출력 파일의 60fps는 실시간 처리 성능을 뜻하지 않습니다. 오디오 없음. 기본 모델은 변경하지 않았습니다.</p>
<p>얇은 물체, 인물/의자 윤곽, 배경의 출렁임을 비교하세요. 정지 화면과 수치만으로 VR 편안함은 판정할 수 없습니다.</p>
'''+''.join(sections)+'''<footer><p>Source: UVG-VCM, Ultra Video Group, Tampere University.
T. Partanen et al., UVG-VCM: Benchmarking dataset for machine-oriented visual data compression, QoMEX 2026.
<a href="https://tie-ultravideo.rd.tuni.fi/UVG-VCM/index.html">Dataset</a> ·
<a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>.
Modified: first 6 seconds, AI depth/stereo synthesis, crop/resize and video encoding. No endorsement.</p></footer></html>'''
    (directory/'review.html').write_text(page, encoding='utf-8')
    print(json.dumps(summary['models'], indent=2), flush=True)


if __name__ == '__main__':
    main()
