"""Explicit bounded non-commercial DA2 Base integration experiment."""
import argparse
import json
from pathlib import Path
import uuid

import cv2
import numpy as np
import torch

from da2_base_experiment import Da2BaseOracle, ROOT
from screento3d_app import pipeline
from screento3d_app.depth_backend import BackendBinding, BackendSpec
from screento3d_app.resources import configure_media_tools
from vda_comparison import BoundedEngine, validate_metadata


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    args = parser.parse_args()
    configure_media_tools(ROOT/'out/gpu-preview/ScreenTo3D-GPU-Preview/_internal/ffmpeg')
    metadata = pipeline.probe_video(args.input)
    validate_metadata(metadata, 124)
    root = ROOT/'out/da2-base-oracle'/uuid.uuid4().hex
    root.mkdir(parents=True)
    report = dict(passed=False, metadata=metadata, note='Non-commercial CUDA oracle; not TensorRT or benchmark')
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    try:
        capture = cv2.VideoCapture(str(args.input))
        try:
            ok, bgr = capture.read()
            if not ok:
                raise ValueError('Cannot read input')
        finally:
            capture.release()
        frame = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        with Da2BaseOracle() as engine:
            actual = engine.infer(frame)
            expected = engine.model.infer_image(bgr, input_size=518)
            np.testing.assert_allclose(actual[0], expected, atol=1e-5, rtol=1e-5)
            saved = actual.copy()
            repeated = engine.infer(frame)
            np.testing.assert_array_equal(actual, saved)
            np.testing.assert_allclose(repeated, actual, atol=1e-5, rtol=1e-5)
            report['reference_max_abs'] = float(np.abs(actual[0]-expected).max())
            report['capability'] = dict(torch=torch.__version__, cuda=torch.version.cuda,
                                       gpu=torch.cuda.get_device_name(), adapter=engine.telemetry())
        engine.close()
        try:
            engine.infer(frame)
        except RuntimeError:
            pass
        else:
            raise AssertionError('Closed adapter allowed inference')
        binding = BackendBinding(BackendSpec('da2-base', 'pytorch-cuda-fp32'),
            lambda progress: BoundedEngine(Da2BaseOracle(progress), 124), lambda rgb: rgb)
        report['conversion'] = pipeline.convert_video(args.input, root/'da2-base.mp4', 'balanced',
            lambda event: None, depth_backend=binding, diagnostic_hashes=True)
        capture = cv2.VideoCapture(str(root/'da2-base.mp4'))
        count = 0
        try:
            while True:
                ok, image = capture.read()
                if not ok:
                    break
                assert image.shape == (metadata['height'], metadata['width']*2, 3)
                count += 1
        finally:
            capture.release()
        assert count == report['conversion']['frames'] == metadata['total_frames']
        report['decoded_frames'] = count
        report['passed'] = True
    finally:
        (root/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(root/'report.json', flush=True)


if __name__ == '__main__':
    main()
