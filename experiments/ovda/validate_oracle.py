# oVDA experiment, NC-SA-UHDV1.0; attribution and terms in README.md/LICENSE.
"""Real CUDA oracle parity across cache fill/rollover, reset and SBS pipeline."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import platform
import subprocess
import threading
import uuid
import cv2
import numpy as np
import torch
from oracle import ROOT, OvdaOracle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True, type=Path)
    args = parser.parse_args()
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    from depthsbs_app import pipeline
    from depthsbs_app.depth_backend import BackendBinding, BackendSpec
    from depthsbs_app.resources import configure_media_tools
    from evaluate_depth_models import inspect_media, sha
    from vda_comparison import BoundedEngine, validate_metadata
    configure_media_tools(ROOT/'out/gpu-preview/DepthSBS-GPU-Preview/_internal/ffmpeg')
    meta = pipeline.probe_video(args.input)
    validate_metadata(meta, 124)
    root = ROOT/'out/ovda-oracle'/uuid.uuid4().hex
    root.mkdir(parents=True)
    print(root, flush=True)
    report = dict(passed=False, input_sha256=sha(args.input), metadata=meta, os=platform.platform(),
                  torch=torch.__version__, gpu=torch.cuda.get_device_name(), comparisons=[],
                  note='Personal noncommercial CUDA oracle, not TensorRT or public app support')
    try:
        capture = cv2.VideoCapture(str(args.input))
        frames = []
        try:
            for _ in range(32):
                ok, frame = capture.read()
                if not ok: raise ValueError('Need at least 32 frames')
                frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        finally: capture.release()
        with OvdaOracle() as engine:
            # Original unmodified full-video routine is the independent cache-handling reference.
            reference = engine.model.infer_video_depth(np.stack(frames), device='cuda:0',
                preprocess_device='cpu', input_size=518, fp32=True)[0]
            engine.reset('start')
            for index, frame in enumerate(frames):
                depth = engine.infer(frame)
                np.testing.assert_allclose(depth[0], reference[index], atol=.001, rtol=.001)
                report['comparisons'].append(dict(frame=index, max_abs=float(np.max(np.abs(depth[0]-reference[index])))))
                if index == 0:
                    first = depth.copy()
                    np.savez_compressed(root/'golden-first.npz', rgb=frame, depth=first)
                assert not np.shares_memory(depth, first)
            report['cache'] = engine.telemetry()
            for reason in ('scene_cut', 'source_change', 'discontinuity'):
                engine.reset(reason)
                np.testing.assert_allclose(engine.infer(frames[0]), first, atol=.001, rtol=.001)
            errors = []
            def foreign():
                try: engine.infer(frames[0])
                except RuntimeError as error: errors.append(str(error))
            thread = threading.Thread(target=foreign); thread.start(); thread.join()
            assert errors
            try: engine.infer(frames[0][:,:-14])
            except ValueError: pass
            else: raise AssertionError('Unreset geometry accepted')
        engine.close()
        try: engine.infer(frames[0])
        except RuntimeError: pass
        else: raise AssertionError('Closed engine accepted')
        print('PASS original 32-frame parity, cache rollover, resets and ownership', flush=True)
        binding = BackendBinding(BackendSpec('ovda-small-c16', 'pytorch-cuda-fp32-experiment', True, True),
            lambda progress: BoundedEngine(OvdaOracle(progress), 124), lambda frame: frame)
        output = root/'ovda-sbs.mp4'
        report['conversion'] = pipeline.convert_video(args.input, output, 'video-quality', lambda e: None,
            depth_backend=binding, diagnostic_hashes=True)
        inspect_media(output, meta)
        assert report['conversion']['frames'] == meta['total_frames']
        print('PASS real SBS pipeline', flush=True)
        report['passed'] = True
    finally:
        (root/'report.json').write_text(json.dumps(report, indent=2))
        print(root/'report.json', flush=True)


if __name__ == '__main__': main()
