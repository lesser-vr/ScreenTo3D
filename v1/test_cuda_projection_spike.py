"""Explicit GPU experiment: exact pixels and host-to-host spatial timing only."""
import ctypes
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import time
import uuid
import numpy as np
from depthsbs_app.stereo import project_eye, guide_depth, refine_flat_background


def main():
    repo = Path(__file__).resolve().parents[1]
    path = repo / 'out/cuda-projection-spike/projection.dll'
    dll = ctypes.CDLL(str(path))
    fn = dll.project_host
    fn.argtypes = [ctypes.c_void_p] * 4 + [ctypes.c_int] * 3
    fn.restype = ctypes.c_int

    def gpu(frame, depth, shift, coverage=True):
        if frame.dtype != np.uint8 or depth.dtype != np.float32 or shift.dtype != np.float32:
            raise ValueError('Expected RGB uint8 and float32 depth/shift')
        h, w = depth.shape
        if not (1 <= h <= 4320 and 1 <= w <= 7680) or frame.shape != (h, w, 3) or shift.shape != (h, w):
            raise ValueError('Invalid image dimensions')
        if not np.isfinite(depth).all() or not np.isfinite(shift).all() or np.max(np.abs(shift)) > 1e6:
            raise ValueError('Invalid depth or shift')
        frame, depth, shift = (np.ascontiguousarray(a) for a in (frame, depth, shift))
        output = np.empty_like(frame)
        status = fn(frame.ctypes.data, depth.ctypes.data, shift.ctypes.data,
                    output.ctypes.data, w, h, int(coverage))
        if status:
            raise RuntimeError(f'CUDA projection failed with status {status}')
        return output

    checks = 0
    def compare(frame, depth, shift, coverage):
        nonlocal checks
        np.testing.assert_array_equal(gpu(frame, depth, shift, coverage),
                                      project_eye(frame, depth, shift, coverage))
        checks += 1

    rng = np.random.default_rng(790)
    for h, w in ((1, 1), (3, 17), (16, 64), (32, 128)):
        for _ in range(12):
            frame = rng.integers(0, 256, (h, w, 3), dtype=np.uint8)
            depth = rng.random((h, w), dtype=np.float32)
            shift = rng.uniform(-w*2, w*2, (h, w)).astype(np.float32)
            for coverage in (False, True):
                compare(frame, depth, shift, coverage)
    frame = rng.integers(0, 256, (5, 32, 3), dtype=np.uint8)
    depth = np.ones((5, 32), np.float32)
    for amount in (0, -2, 2, -100, 100, -.5, .5):
        for coverage in (False, True):
            compare(frame, depth, np.full_like(depth, amount), coverage)
    sample = np.load(repo / 'out/stereo-ghost-diagnosis/sample.npz')
    frame = sample['frame']
    for name in ('normalized', 'ema'):
        depth = refine_flat_background(frame, guide_depth(frame, sample[name]))
        shift = ((depth - .45) * frame.shape[1] * .026 * .5).astype(np.float32)
        for sign in (-1, 1):
            compare(frame, depth, shift * sign, True)

    timings = {}
    for name, operation in (('cpu', lambda: project_eye(frame, depth, shift, True)),
                            ('gpu_host_to_host', lambda: gpu(frame, depth, shift))):
        operation()
        samples = []
        for _ in range(30):
            start = time.perf_counter()
            operation()
            samples.append((time.perf_counter() - start) * 1000)
        timings[name] = {'median_ms': statistics.median(samples), 'samples_ms': samples}
    report = dict(exact_pixel_checks=checks, timings=timings,
        build=json.loads((path.parent / 'build-manifest.json').read_text(encoding='utf-8-sig')),
        gpu=subprocess.check_output(['nvidia-smi', '--query-gpu=name,driver_version,compute_cap', '--format=csv,noheader'], text=True).strip(),
        width=frame.shape[1], height=frame.shape[0],
        scope='One eye only; GPU includes validation, allocation, copies, sync and frees. Not video FPS.',
        dll_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        source_sha256=hashlib.sha256((repo / 'experiments/cuda_projection/projection.cu').read_bytes()).hexdigest())
    output = path.parent / f'validation-{uuid.uuid4().hex}.json'
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k: v['median_ms'] for k, v in timings.items()}))
    print(f'PASS: {checks} exact-pixel checks')
    print(output)


if __name__ == '__main__':
    main()
