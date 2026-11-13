"""Bounded same-policy DA2/VDA review artifacts; not a quality ranking."""
import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import uuid
from unittest.mock import patch

import cv2
import numpy as np

from screento3d_app import pipeline
from screento3d_app.depth_backend import resolve_backend, vda_binding
from screento3d_app.resources import configure_media_tools
from screento3d_app.vda_artifacts import sha256
from vda_comparison import BoundedEngine, validate_metadata, validate_runs, inspection_sheet

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--engine-dir', type=Path, default=ROOT/'out/vda-local')
    parser.add_argument('--runtime-dir', type=Path, default=Path('C:/TensorRT/TensorRT-11.2.1.2/bin'))
    parser.add_argument('--max-frames', type=int, default=124)
    parser.add_argument('--da2-model', type=Path, default=ROOT/'out/models/da2-small/model_fp16.onnx')
    args = parser.parse_args()
    configure_media_tools(ROOT/'out/gpu-preview/ScreenTo3D-GPU-Preview/_internal/ffmpeg')
    metadata = pipeline.probe_video(args.input)
    validate_metadata(metadata, args.max_frames)
    vda = vda_binding(args.engine_dir, args.runtime_dir)
    vda.input_validator(metadata)
    model = args.da2_model.resolve()
    if not model.is_file():
        raise FileNotFoundError(model)
    root = ROOT/'out/depth-model-comparison'/uuid.uuid4().hex
    root.mkdir(parents=True)
    report = dict(passed=False, input=str(args.input.resolve()), input_sha256=sha256(args.input),
                  metadata=metadata, da2_onnx_sha256=sha256(model), runs={},
                  note='Same Video Quality stereo/encode policy; native model preprocessing differs. '
                       'Diagnostic hashing timings are not benchmark or quality rankings.')
    try:
        # Retain the DLL directory handle until both sequential backends are closed.
        with os.add_dll_directory(str(args.runtime_dir.resolve())):
            from screento3d_app import trt_backend
            def da2_factory(progress):
                # Diagnostic-only explicit model location; production lookup stays unchanged.
                with patch.object(trt_backend, '_model_path', return_value=model):
                    return trt_backend.DepthEngine(progress)
            bindings = [('da2-small', resolve_backend('da2-small', da2_factory, pipeline.preprocess)),
                        ('vda-small', vda)]
            for name, binding in bindings:
                factory = binding.engine_factory
                bounded = replace(binding, engine_factory=lambda progress, factory=factory:
                                  BoundedEngine(factory(progress), args.max_frames))
                report['runs'][name] = pipeline.convert_video(args.input, root/f'{name}.mp4',
                    'video-quality', lambda event: None, diagnostic_hashes=True, depth_backend=bounded)
                print('Converted: '+name, flush=True)
        count = report['runs']['da2-small']['frames']
        validate_runs(report['runs'], metadata['total_frames'], count)
        report['outputs'] = {}
        for name in report['runs']:
            # Input preflight doubles width; do not apply it to an already-SBS output.
            probe = pipeline._run([pipeline._tool('ffprobe'), '-v', 'error', '-show_streams',
                                   '-of', 'json', str(root/f'{name}.mp4')])
            if probe.returncode:
                raise RuntimeError(probe.stderr)
            streams = json.loads(probe.stdout)['streams']
            video = next(stream for stream in streams if stream['codec_type'] == 'video')
            output = dict(width=int(video['width']), height=int(video['height']),
                          total_frames=int(video['nb_frames']),
                          has_audio=any(stream['codec_type'] == 'audio' for stream in streams))
            if (output['width'], output['height'], output['total_frames'], output['has_audio']) != (
                    metadata['width']*2, metadata['height'], count, metadata['has_audio']):
                raise ValueError('Output geometry, count or audio mismatch')
            report['outputs'][name] = output
        captures = [cv2.VideoCapture(str(path)) for path in
                    (args.input, root/'da2-small.mp4', root/'vda-small.mp4')]
        try:
            for index in range(count):
                decoded = [capture.read() for capture in captures]
                if not all(ok for ok, _ in decoded):
                    raise ValueError('Missing decoded frame')
                source, da2, vda_frame = [frame for _, frame in decoded]
                h, w = metadata['height'], metadata['width']
                if source.shape != (h, w, 3) or any(f.shape != (h, w*2, 3) for f in (da2, vda_frame)):
                    raise ValueError('Decoded geometry mismatch')
                if index in {min(20, count-1), count//2, min(100, count-1)}:
                    rows = [('SOURCE duplicated', np.concatenate([source, source], axis=1)),
                            ('DA2 Small - left / right', da2), ('VDA Small FP32 - left / right', vda_frame)]
                    for kind, lower in [('hands', True), ('eyes', False)]:
                        if not cv2.imwrite(str(root/f'{kind}-{index}.png'), inspection_sheet(rows, w, h, lower=lower)):
                            raise RuntimeError('Failed to save inspection sheet')
            if any(capture.read()[0] for capture in captures):
                raise ValueError('Unexpected extra frames')
        finally:
            for capture in captures:
                capture.release()
        if sha256(args.input) != report['input_sha256']:
            raise ValueError('Input changed during comparison')
        report['passed'] = True
    finally:
        (root/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(root/'report.json', flush=True)


if __name__ == '__main__':
    main()
