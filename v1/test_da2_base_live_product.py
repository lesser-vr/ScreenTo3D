"""Base raw-depth parity, legacy SBS tolerance and exact native/host parity."""
import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from depthsbs_app.da2_base import binding
from depthsbs_app.desktop_jobs import ROOT, BUNDLE
from depthsbs_app.resources import configure_resource_root
from depthsbs_app.pipeline import StereoSynthesizer
from depthsbs_app.stereo import guide_depth
from depthsbs_app.live_projection import LiveProjection as factory
from depthsbs_app.live_policy import resolve_live
from depthsbs_app.live_source_gpu_candidate import LiveSourceGpuCandidate
from depthsbs_app.live_source_gpu_texture import LiveSourceGpuTexture
from public_test_media import CORPUS, SOURCES
from test_ovda_device_post import load_frames


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sizes', default='1920x1080,3440x1440,1080x1920,3840x2160')
    parser.add_argument('--gpu-input', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    configure_resource_root(BUNDLE)
    runtime = Path('C:/TensorRT/TensorRT-11.2.1.2/bin')
    policy = resolve_live('balanced')
    source_path = CORPUS / 'FloorballGame.mp4'
    source_record = json.loads(source_path.with_suffix('.json').read_text())
    digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
    assert digest == source_record['sha256']
    assert source_record['source_sha256'] == SOURCES['FloorballGame']
    source = load_frames(source_path, 6)
    report = dict(passed=False, cases=[], limits=dict(depth_mae=1e-6, depth_max=1e-4,
        rgb_mae=.05, rgb_changed_fraction=.001), input_sha256=digest,
        scope='Raw depth exact; existing live-GPU numerical tolerance vs legacy CPU post/CUDA SBS; native vs GPU-host exact. Not continuous/VR review.')
    try:
        for size in args.sizes.split(','):
            width, height = map(int, size.split('x'))
            with ExitStack() as stack:
                stack.enter_context(os.add_dll_directory(str(runtime)))
                engines = []
                for device_depth in (False, True):
                    backend = binding(ROOT/'out/da2-base-local', runtime, device_depth=device_depth)
                    backend.input_validator(dict(width=width, height=height))
                    engines.append(stack.enter_context(backend.engine_factory(None)))
                host, device = engines
                projection = stack.enter_context(factory(width, height))
                guided = []
                def guide(*values, **options):
                    value = guide_depth(*values, **options)
                    guided[:] = [value.copy()]
                    return value
                reference = StereoSynthesizer(width, height, policy, projection, paired_projection=projection.project_pair)
                product = stack.enter_context(LiveSourceGpuCandidate(width, height, policy, device))
                cpu_input = stack.enter_context(LiveSourceGpuCandidate(width, height, policy, device)) if args.gpu_input else None
                native = stack.enter_context(LiveSourceGpuTexture(width, height, policy, device, diagnostic=True))
                readback = np.empty((height, width*2, 4), np.uint8)
                for index, image in enumerate(source):
                    frame = cv2.resize(image, (width, height))
                    if index == 3:
                        frame = 255 - frame  # Cut/reset case.
                    if index == 5:
                        frame[:] = 112  # Flat-background branch.
                        cv2.rectangle(frame, (width//3, height//3), (width*2//3, height*2//3), (180,80,50), -1)
                    raw = host.infer(frame)
                    # Compare the same stage: diagnostic GPU aligned depth is
                    # before optional flat-background refinement.
                    with patch('depthsbs_app.pipeline.guide_depth', side_effect=guide):
                        expected = reference.render(frame, raw)
                    input_frame = frame
                    if args.gpu_input:
                        from depthsbs_app.gpu_frame import GpuFrame
                        bgra = cv2.cvtColor(frame, cv2.COLOR_RGB2BGRA)
                        with device.torch.cuda.stream(device.stream):
                            input_frame = GpuFrame(device.torch.from_numpy(bgra).cuda(), device)
                        assert np.array_equal(input_frame.thumbnail(), cv2.resize(frame, (32,32)))
                        assert product.needs_background(input_frame) == product.needs_background(frame)
                    token = product.infer(input_frame)
                    device.stream.synchronize()
                    actual_depth = token.tensor.cpu().numpy()
                    assert np.array_equal(raw, actual_depth), 'Raw depth mismatch'
                    # A second inference must not overwrite an outstanding token.
                    try:
                        device.infer_device(frame)
                    except RuntimeError:
                        pass
                    else:
                        raise AssertionError('Pending token reused')
                    actual, aligned = product.render(input_frame, token, diagnostic=True)
                    if cpu_input is not None:
                        cpu_result = cpu_input.render(frame, cpu_input.infer(frame))
                        assert np.array_equal(actual, cpu_result), 'GPU input changed SBS pixels'
                    try:
                        token.validate()
                    except RuntimeError:
                        pass
                    else:
                        raise AssertionError('Completed token still valid')
                    native.slot = index % 2
                    slot = native.render(input_frame, native.infer(input_frame))
                    native.pool.check(native.pool.dll.live_pool_readback(native.pool.handle, slot, readback.ctypes.data))
                    assert np.array_equal(actual, readback[:,:,:3]) and np.all(readback[:,:,3] == 255)
                    diff = np.abs(aligned - guided[0])
                    pixel = np.abs(actual.astype(np.int16) - expected.astype(np.int16))
                    row = dict(size=size, frame=index, raw_exact=True, native_exact=True,
                        gpu_input=args.gpu_input, input_sbs_exact=True if args.gpu_input else None,
                        depth_mae=float(diff.mean()), depth_max=float(diff.max()),
                        rgb_mae=float(pixel.mean()), rgb_changed_fraction=float(np.mean(np.any(pixel != 0, axis=2))))
                    row['passed'] = all(row[k] <= v for k,v in report['limits'].items())
                    report['cases'].append(row)
                    print(json.dumps(row), flush=True)
                    if index == 2:
                        cv2.imwrite(str(args.output/f'{size}-reference.png'), cv2.cvtColor(expected, cv2.COLOR_RGB2BGR))
                        cv2.imwrite(str(args.output/f'{size}-gpu.png'), cv2.cvtColor(actual, cv2.COLOR_RGB2BGR))
                    assert row['passed'], 'Existing GPU parity limits exceeded'
                assert not device.pending_device and device.device_completions == len(source)*(3 if args.gpu_input else 2)
        report['passed'] = True
    finally:
        (args.output/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
