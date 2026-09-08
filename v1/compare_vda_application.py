"""Matched FP32 source/TRT application comparison; not a quality ranking."""
import argparse
from contextlib import ExitStack
from dataclasses import replace
import json
from pathlib import Path
import uuid

import cv2
import numpy as np
import torch

from depthsbs_app import pipeline
from depthsbs_app.depth_backend import vda_binding
from depthsbs_app.resources import configure_media_tools
from depthsbs_app.vda_backend import VdaEngine
from depthsbs_app.vda_artifacts import artifact_profiles, select_artifact, load_manifest, sha256
from vda_streaming_experiment import ROOT, VdaStreamingEngine
from vda_comparison import BoundedEngine, validate_metadata, validate_runs, inspection_sheet


def fp32_oracle():
    engine = VdaStreamingEngine()
    original = engine.model.infer_video_depth_one
    def infer(*args, **kwargs):
        kwargs['fp32'] = True
        return original(*args, **kwargs)
    engine.model.infer_video_depth_one = infer
    return engine


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--engine-dir', type=Path, default=ROOT/'out/vda-local')
    parser.add_argument('--runtime-dir', type=Path, default=Path('C:/TensorRT/TensorRT-11.2.1.2/bin'))
    parser.add_argument('--max-frames', type=int, default=124)
    args = parser.parse_args()
    configure_media_tools(ROOT/'out/gpu-preview/DepthSBS-GPU-Preview/_internal/ffmpeg')
    metadata = pipeline.probe_video(args.input)
    validate_metadata(metadata, args.max_frames)
    selected = select_artifact(artifact_profiles(args.engine_dir), metadata)
    binding = vda_binding(selected, args.runtime_dir)
    manifest = load_manifest(selected)
    root = ROOT/'out/vda-application-comparison'/uuid.uuid4().hex
    root.mkdir(parents=True)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    report = dict(passed=False, depth_comparisons=[], runs={}, metadata=metadata,
        profile=manifest['input_shape'], engine_hashes={name: record['sha256'] for name, record in manifest['engines'].items()},
        frame_budget=args.max_frames, source_revision=manifest['source_revision'],
        input_sha256=sha256(args.input), weight_sha256=manifest['weight_sha256'],
        note='Matched implementation agreement, not quality superiority or benchmark; paired source inference and hashing inflate timing')

    class PairedEngine:
        def __init__(self):
            self.stack = ExitStack()
            try:
                self.engine = self.stack.enter_context(VdaEngine(selected, args.runtime_dir))
                self.oracle = self.stack.enter_context(fp32_oracle())
            except BaseException:
                self.stack.close()
                raise
        def infer(self, frame):
            result, expected = self.engine.infer(frame), self.oracle.infer(frame)
            delta = np.abs(result-expected)
            np.testing.assert_allclose(result, expected, atol=.001, rtol=.001)
            report['depth_comparisons'].append(dict(max_abs=float(delta.max()), mean_abs=float(delta.mean())))
            return result
        def reset(self, reason):
            self.engine.reset(reason)
            self.oracle.reset(reason)
        def telemetry(self):
            return self.engine.telemetry()
        def close(self):
            self.stack.close()
        def __enter__(self):
            return self
        def __exit__(self, *exc):
            return self.stack.__exit__(*exc)

    try:
        for name, runtime, factory in (('trt-fp32', 'tensorrt-fp32', PairedEngine),
                              ('source-fp32', 'pytorch-cuda-fp32', fp32_oracle),
                              ('source-autocast', 'pytorch-cuda-autocast', VdaStreamingEngine)):
            report['runs'][name] = pipeline.convert_video(args.input, root/f'{name}.mp4', 'video-quality',
                lambda event: None, diagnostic_hashes=True, depth_backend=replace(binding,
                    spec=replace(binding.spec, runtime=runtime),
                    engine_factory=lambda progress: BoundedEngine(factory(), args.max_frames)))
            print('PASS: '+name, flush=True)
        validate_runs(report['runs'], metadata['total_frames'], len(report['depth_comparisons']))
        if sha256(args.input) != report['input_sha256']:
            raise ValueError('Source file changed during comparison')
        captures = [cv2.VideoCapture(str(root/f'{name}.mp4')) for name in ('trt-fp32', 'source-fp32', 'source-autocast')]
        source = cv2.VideoCapture(str(args.input))
        stats = [dict(sum_abs=0, values=0, max_abs=0, different_values=0) for _ in range(2)]
        try:
            for index in range(report['runs']['trt-fp32']['frames']):
                frames = [capture.read() for capture in captures]
                ok, original = source.read()
                if not ok or not all(ok for ok, _ in frames):
                    raise ValueError('Missing decoded comparison frame')
                images = [image for _, image in frames]
                if original.shape != (metadata['height'], metadata['width'], 3) or any(image.shape !=
                        (metadata['height'], metadata['width']*2, 3) for image in images):
                    raise ValueError('Decoded comparison geometry changed')
                for stat, other in zip(stats, images[1:]):
                    delta = np.abs(images[0].astype(np.int16)-other.astype(np.int16))
                    stat['sum_abs'] += int(delta.sum())
                    stat['values'] += delta.size
                    stat['max_abs'] = max(stat['max_abs'], int(delta.max()))
                    stat['different_values'] += int(np.count_nonzero(delta))
                if index in {0, report['runs']['trt-fp32']['frames']//2, report['runs']['trt-fp32']['frames']-1}:
                    width = original.shape[1]
                    rows = []
                    for label, image in [('SOURCE duplicated', np.concatenate([original, original], axis=1)),
                        ('TRT FP32 - left / right', images[0]), ('Source FP32 - left / right', images[1]),
                        ('Source autocast - left / right', images[2])]:
                        rows.append((label, image))
                    for filename, lower in ((f'eyes-{index}.jpg', False), (f'hands-{index}.png', True)):
                        if not cv2.imwrite(str(root/filename), inspection_sheet(rows, width, original.shape[0], lower=lower)):
                            raise RuntimeError('Failed to write comparison inspection image')
            if source.read()[0] or any(capture.read()[0] for capture in captures):
                raise ValueError('Unexpected extra decoded comparison frames')
            report['decoded_comparisons'] = {
                name: dict(mean_abs=stat['sum_abs']/stat['values'], max_abs=stat['max_abs'],
                    different_fraction=stat['different_values']/stat['values'])
                for name, stat in zip(('trt_vs_source_fp32', 'trt_vs_source_autocast'), stats)}
        finally:
            source.release()
            for capture in captures:
                capture.release()
        report['passed'] = True
    finally:
        (root/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(root/'report.json', flush=True)


if __name__ == '__main__':
    main()
