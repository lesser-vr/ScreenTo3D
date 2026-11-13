"""Hair close-up and actual VDA fresh-engine scene-reset diagnostic."""
import argparse
import json
from pathlib import Path
import platform
import subprocess
import sys
import uuid
import cv2
import numpy as np
from evaluate_depth_models import ROOT, sha, inspect_media
from evaluate_live_action import MODELS, review
from vda_comparison import validate_runs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live-root', required=True, type=Path)
    args = parser.parse_args()
    from screento3d_app.resources import configure_media_tools
    from screento3d_app import pipeline
    from screento3d_app.depth_backend import vda_binding
    media = ROOT/'out/gpu-preview/ScreenTo3D-GPU-Preview/_internal/ffmpeg'
    configure_media_tools(media)
    root = ROOT/'out/live-action-supplement'/uuid.uuid4().hex
    root.mkdir(parents=True)
    source = ROOT/'out/public-video-source/uvg-vcm/Beauty.hevc'
    source_hash = '88af90a616635b1a8b726d0260d724da9f662aaf321e5c376eab9ed8ce1eed7f'
    assert sha(source) == source_hash
    attribution = ('Beauty, copyright Digiturk, distributed by Ultra Video Group, Tampere University, CC BY-NC 3.0. '
        'https://tie-ultravideo.rd.tuni.fi/dataset.html ; https://creativecommons.org/licenses/by-nc/3.0/ . '
        'A. Mercat, M. Viitanen, J. Vanne, UVG dataset: 50/120fps 4K sequences for video codec analysis and development, MMSys 2020. '
        'Local non-commercial diagnostic only; do not bundle or promote commercially. '
        'Official HEVC excerpt frames 0-119, source-declared 120fps (raw elementary stream has no reliable container timestamps), '
        '3840x2160 downsampled to 1280x720, H264 CRF18, no audio, no crop/padding. SBS AI-estimated derivatives.')
    (root/'ATTRIBUTION.txt').write_text(attribution)
    report = dict(passed=False, attribution=attribution, source_sha256=source_hash,
        source_url='https://tie-ultravideo.rd.tuni.fi/video/Beauty_3840x2160_120fps_420_8bit_HEVC_RAW.hevc',
        runs={}, os=platform.platform(), git_head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        git_dirty=bool(subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip()),
        gpu=subprocess.check_output(['nvidia-smi', '--query-gpu=name,driver_version,memory.total,memory.used,utilization.gpu', '--format=csv'], text=True))
    print(root, flush=True)
    try:
        clip = root/'input.mp4'
        subprocess.run([str(media/'ffmpeg.exe'), '-v', 'error', '-r', '120', '-i', str(source), '-frames:v', '120',
            '-vf', 'scale=1280:720:flags=lanczos', '-c:v', 'libx264', '-crf', '18', '-pix_fmt', 'yuv420p', str(clip)], check=True)
        metadata = pipeline.probe_video(clip)
        assert (metadata['width'], metadata['height'], metadata['total_frames'], metadata['fps'], metadata['has_audio']) == (1280, 720, 120, 120, False)
        report.update(metadata=metadata, input_sha256=sha(clip))
        for model in MODELS:
            output = root/f'{model}.mp4'
            with (root/f'{model}.log').open('w') as log:
                subprocess.run([sys.executable, str(ROOT/'v1/evaluate_live_action.py'), '--one', model,
                    '--input', str(clip), '--output', str(output)], check=True, stdout=log, stderr=subprocess.STDOUT)
            report['runs'][model] = json.loads(output.with_suffix('.json').read_text())
            inspect_media(output, metadata)
            print('PASS Beauty / '+model, flush=True)
        validate_runs(report['runs'], 120, 120)
        review(root, 120, 120)
        # Same exact decoded frames, no codec differences between the reset and fresh cases.
        capture = cv2.VideoCapture(str(args.live_root/'KnownCut/input.mp4'))
        prior = []
        try:
            for index in range(61):
                ok, frame = capture.read(); assert ok
                if index < 8: prior.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                if index == 60: target = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        finally: capture.release()
        binding = vda_binding(ROOT/'out/vda-local', Path('C:/TensorRT/TensorRT-11.2.1.2/bin'))
        binding.input_validator(dict(width=1280, height=720))
        with binding.engine_factory(None) as engine:
            binding.reset(engine, 'start')
            for frame in prior: binding.infer(engine, binding.prepare(frame))
            binding.reset(engine, 'scene_cut')
            reset_depth = binding.infer(engine, binding.prepare(target))
            reset_telemetry = engine.telemetry()
        with binding.engine_factory(None) as engine:
            binding.reset(engine, 'start')
            fresh_depth = binding.infer(engine, binding.prepare(target))
        maximum = float(np.max(np.abs(reset_depth-fresh_depth)))
        np.testing.assert_allclose(reset_depth, fresh_depth, atol=.001, rtol=.001)
        report['vda_reset_vs_fresh'] = dict(max_abs=maximum, atol=.001, rtol=.001,
            prior_frames=8, annotated_cut_frame=60, reset_telemetry=reset_telemetry,
            note='Real input post-cut frame after prior streaming history vs separately created fresh engine')
        report['passed'] = True
    finally:
        (root/'report.json').write_text(json.dumps(report, indent=2))
        print(root/'report.json', flush=True)


if __name__ == '__main__': main()
