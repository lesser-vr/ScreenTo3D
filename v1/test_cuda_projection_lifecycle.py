"""Real-GPU experimental allocation/teardown and persistent parity checks."""
import ctypes
import json
from pathlib import Path
import statistics
import time
import uuid
import numpy as np
from cuda.bindings import runtime as cudart
from cuda_projection_experiment import CudaProjection
from screento3d_app.stereo import project_eye


def memory_used():
    error, free, total = cudart.cudaMemGetInfo()
    if error != cudart.cudaError_t.cudaSuccess:
        raise RuntimeError(f'GPU memory query failed: {error}')
    return int(total - free)


def main():
    repo = Path(__file__).resolve().parents[1]
    path = repo / 'out/cuda-projection-spike/projection.dll'
    dll = ctypes.CDLL(str(path))
    inject = dll.projection_create_injected
    inject.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_int, ctypes.c_int, ctypes.c_int]
    inject.restype = ctypes.c_int
    rng = np.random.default_rng(22)
    frame = rng.integers(0, 256, (64, 128, 3), dtype=np.uint8)
    depth = rng.random((64, 128), dtype=np.float32)
    shift = ((depth - .5) * 12).astype(np.float32)
    expected = project_eye(frame, depth, shift, True)
    with CudaProjection(128, 64) as warm:
        warm.project(frame, depth, shift, True)
    observations = [memory_used()]
    for _ in range(20):
        with CudaProjection(128, 64) as owner:
            for _ in range(3):
                np.testing.assert_array_equal(owner.project(frame, depth, shift, True), expected)
        owner.close()
        observations.append(memory_used())
    for _ in range(10):
        for stage in range(1, 7):
            handle = ctypes.c_void_p()
            status = inject(ctypes.byref(handle), 1056, 608, stage)
            assert status != 0 and handle.value is None
            observations.append(memory_used())
    sample = np.load(repo / 'out/stereo-ghost-diagnosis/sample.npz')
    frame, depth = sample['frame'], sample['normalized']
    shift = ((depth - .45) * 10).astype(np.float32)
    with CudaProjection(frame.shape[1], frame.shape[0]) as owner:
        np.testing.assert_array_equal(owner.project(frame, depth, shift, True), project_eye(frame, depth, shift, True))
        timings = []
        for _ in range(30):
            start = time.perf_counter()
            owner.project(frame, depth, shift, True)
            timings.append((time.perf_counter() - start) * 1000)
    report = dict(success_cycles=20, allocation_failure_cycles=60,
        memory_scope='device-global sampled, not proof of leak freedom or device-loss handling',
        used_bytes_after_close=observations, persistent_one_eye_median_ms=statistics.median(timings),
        timing_scope='host validation/copies/kernels/sync; excludes create/close and full video stages')
    output = path.parent / f'lifecycle-{uuid.uuid4().hex}.json'
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'used_bytes_after_close'}))
    print('Observed used-byte range:', min(observations), max(observations))
    print(output)


if __name__ == '__main__':
    main()
