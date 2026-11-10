"""Real-device parity check for VDA window preprocessing and temporal inference."""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np
import torch

from depthsbs_app.desktop_jobs import BUNDLE
from depthsbs_app.gpu_frame import GpuFrame
from depthsbs_app.resources import configure_resource_root
from depthsbs_app.vda_artifacts import artifact_profiles, select_artifact
from depthsbs_app.vda_device import VdaDeviceEngine
from depthsbs_app.vda_preprocess import preprocess


def compare(video, profiles, width, height, count):
    path = select_artifact(profiles, dict(width=width, height=height))
    source = cv2.VideoCapture(str(video))
    input_max = depth_max = 0.0
    try:
        with (VdaDeviceEngine(path, BUNDLE/'runtime') as host,
              VdaDeviceEngine(path, BUNDLE/'runtime') as gpu):
            shape = gpu.input_shape[-2:]
            for i in range(count):
                ok, decoded = source.read()
                if not ok:
                    raise ValueError('Public test input is too short')
                if i == count-2:
                    host.reset('scene_cut')
                    gpu.reset('scene_cut')
                bgra = cv2.cvtColor(cv2.resize(decoded, (width, height)), cv2.COLOR_BGR2BGRA)
                rgb = cv2.cvtColor(bgra, cv2.COLOR_BGRA2RGB)
                with torch.cuda.stream(gpu.stream):
                    frame = GpuFrame(torch.from_numpy(bgra).to(gpu.device), gpu)
                    actual = gpu.gpu_input.prepare(frame.rgb, shape)[0].cpu().numpy()
                expected = preprocess(rgb, shape)
                np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-5)
                input_max = max(input_max, float(np.abs(actual-expected).max()))
                a, b = host.infer_device(rgb), gpu.infer_device(frame)
                a.validate()
                b.validate()
                if gpu.last_input_bytes != 0 or frame.readback_bytes != 0:
                    raise AssertionError('Unexpected host transfer during GPU inference')
                expected, actual = a.tensor.cpu().numpy(), b.tensor.cpu().numpy()
                np.testing.assert_allclose(actual, expected, rtol=.001, atol=.001)
                depth_max = max(depth_max, float(np.abs(actual-expected).max()))
                host.complete_device(a)
                gpu.complete_device(b)
    finally:
        source.release()
    return dict(width=width, height=height, frames=count, input_max_abs=input_max, depth_max_abs=depth_max)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', type=Path, required=True)
    parser.add_argument('--engine-dir', type=Path, required=True)
    args = parser.parse_args()
    configure_resource_root(BUNDLE)
    profiles = artifact_profiles(args.engine_dir)
    # Cross the 42-entry history eviction boundary before the 1080p cut.
    for case in [(1920,1080,48),(3840,2160,5),(3440,1440,5),(1080,1920,5),(1440,1080,5),(1056,608,5)]:
        print(json.dumps(compare(args.video, profiles, *case)), flush=True)
