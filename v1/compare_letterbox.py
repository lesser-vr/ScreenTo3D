"""Same-frame/same-depth letterbox A/B. Never changes application defaults."""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import subprocess
import uuid
from unittest.mock import patch

import cv2
import numpy as np

from depthsbs_app import pipeline
from depthsbs_app.config import MODES
from depthsbs_app.depth_backend import vda_binding
from depthsbs_app.resources import configure_media_tools
from letterbox_refinement import detect_content, refine_padding_background, restore_padding
from vda_comparison import inspection_sheet, validate_metadata

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def encoder(path, width, height, fps, policy):
    with path.with_suffix('.log').open('wb') as log:
        process = subprocess.Popen([pipeline._tool('ffmpeg'), '-v', 'error', '-f', 'rawvideo',
            '-pix_fmt', 'rgb24', '-s', f'{width}x{height}', '-r', str(fps), '-i', 'pipe:0',
            '-an', '-c:v', 'h264_nvenc', '-preset', policy.nvenc_preset, '-cq', str(policy.cq),
            '-pix_fmt', 'yuv420p', str(path)], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            yield process
            process.stdin.close()
            if process.wait(timeout=30):
                raise RuntimeError('A/B video encoder failed')
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
            if process.stdin is not None:
                process.stdin.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    args = parser.parse_args()
    configure_media_tools(ROOT/'out/gpu-preview/DepthSBS-GPU-Preview/_internal/ffmpeg')
    meta = pipeline.probe_video(args.input)
    validate_metadata(meta, 124)
    binding = vda_binding(ROOT/'out/vda-local', Path('C:/TensorRT/TensorRT-11.2.1.2/bin'))
    binding.input_validator(meta)
    root = ROOT/'out/vda-letterbox'/uuid.uuid4().hex
    root.mkdir(parents=True)
    report = dict(passed=False, scope='Controlled same-inference A/B, not production policy or performance',
                  frames=0, refined_frames=0, preserved_padding_frames=0, regions=[], inspection_frames=[])
    policy = MODES['video-quality']
    baseline = pipeline.StereoSynthesizer(meta['width'], meta['height'], policy)
    candidate = pipeline.StereoSynthesizer(meta['width'], meta['height'], policy)
    capture = cv2.VideoCapture(str(args.input))
    decoded_hash, depth_hash = hashlib.sha256(), hashlib.sha256()
    region = None
    def refine(frame, depth, **options):
        nonlocal region
        refined = refine_padding_background(frame, depth, **options)
        region = detect_content(frame) if refined is not depth else None
        return refined
    try:
        with encoder(root/'baseline.video.mp4', meta['width']*2, meta['height'], meta['fps'], policy) as a, \
                encoder(root/'candidate.video.mp4', meta['width']*2, meta['height'], meta['fps'], policy) as b, \
                binding.engine_factory(None) as engine:
            engine.reset('start')
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                index = report['frames']
                if index >= 124:
                    raise ValueError('Actual source exceeds the A/B frame budget')
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                if baseline.is_scene_cut(frame):
                    engine.reset('scene_cut')
                depth = binding.infer(engine, binding.prepare(frame))
                before_frame, before_depth = frame.copy(), depth.copy()
                decoded_hash.update(frame.tobytes()); depth_hash.update(depth.tobytes())
                old = baseline.render(frame, depth)
                with patch('depthsbs_app.pipeline.refine_flat_background', side_effect=refine):
                    new = candidate.render(frame, depth)
                new = restore_padding(new, frame, region)
                np.testing.assert_array_equal(frame, before_frame)
                np.testing.assert_array_equal(depth, before_depth)
                if region is not None:
                    report['refined_frames'] += 1
                    bounds = [region.x0, region.y0, region.x1, region.y1]
                    if bounds not in report['regions']:
                        report['regions'].append(bounds)
                    outside = np.ones(frame.shape[:2], bool)
                    outside[region.y0:region.y1, region.x0:region.x1] = False
                    for eye in (new[:, :meta['width']], new[:, meta['width']:]):
                        np.testing.assert_array_equal(eye[outside], frame[outside])
                    report['preserved_padding_frames'] += 1
                a.stdin.write(old.tobytes()); b.stdin.write(new.tobytes())
                if index in (20, 62, 100):
                    rows = [(label, cv2.cvtColor(value, cv2.COLOR_RGB2BGR)) for label, value in
                        [('Source - duplicated', np.concatenate([frame, frame], axis=1)),
                         ('Baseline - left / right', old), ('Candidate - left / right', new)]]
                    for kind, lower in (('eyes', False), ('hands', True)):
                        if not cv2.imwrite(str(root/f'{kind}-{index}.png'), inspection_sheet(rows, meta['width'], meta['height'], lower=lower)):
                            raise RuntimeError('A/B image write failed')
                    report['inspection_frames'].append(index)
                report['frames'] += 1
            report['engine'] = engine.telemetry()
        if report['frames'] == 0 or (meta['total_frames'] and report['frames'] != meta['total_frames']):
            raise ValueError('A/B source frame count mismatch')
        for name in ('baseline', 'candidate'):
            output = root/f'{name}.mp4'
            result = pipeline._run([pipeline._tool('ffmpeg'), '-v', 'error', '-i', str(root/f'{name}.video.mp4'),
                '-i', str(args.input), '-map', '0:v:0', '-map', '1:a:0?', '-c', 'copy', str(output)])
            if result.returncode:
                raise RuntimeError('A/B audio mux failed: '+result.stderr)
            out = pipeline.probe_video(output, output_codec='hevc')
            if (out['total_frames'] != report['frames'] or out['width'] != meta['width']*2 or
                    out['height'] != meta['height'] or out['has_audio'] != meta['has_audio']):
                raise ValueError('A/B output validation failed')
        report.update(passed=True, decoded_hash=decoded_hash.hexdigest(), depth_hash=depth_hash.hexdigest(),
                      baseline_refined_frames=baseline.flat_background_frames,
                      candidate_refined_frames=candidate.flat_background_frames)
    finally:
        capture.release()
        (root/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(root/'report.json', flush=True)


if __name__ == '__main__':
    main()
