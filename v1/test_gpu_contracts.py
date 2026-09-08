"""Bounded real CUDA parity/lifetime checks against the currently trusted local DLL."""
import argparse
import ctypes
import json
import hashlib
from pathlib import Path

import numpy as np

from depthsbs_app.local_projection import checked_dll, factory
from depthsbs_app.stereo import project_eye


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--fault-fixture', required=True, type=Path, help='Trusted local test-only build directory')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(status='failed', scope='Synthetic GPU parity/close and injected allocation failures; not device-loss or leak-freedom proof')
    try:
        # Reuse production provenance checks; never load an arbitrary test DLL.
        path = checked_dll()
        rng = np.random.default_rng(724)
        frame = rng.integers(0, 256, (64, 128, 3), dtype=np.uint8)
        depth = rng.random((64, 128), dtype=np.float32)
        shift = ((depth - .5) * 12).astype(np.float32)
        expected = project_eye(frame, depth, shift, True)
        for cycle in range(20):
            with factory(128, 64) as owner:
                for repetition in range(3):
                    np.testing.assert_array_equal(owner.project(frame, depth, shift, True), expected)
            owner.close()
            assert not owner.handle.value
            try:
                owner.project(frame, depth, shift, True)
            except RuntimeError:
                pass
            else:
                raise AssertionError('Closed owner remained usable')
        dll = ctypes.CDLL(str(path))
        assert not hasattr(dll, 'projection_create_injected'), 'Fault entry point exposed in production DLL'
        fixture = args.fault_fixture.resolve()
        manifest = json.loads((fixture/'build-manifest.json').read_text(encoding='utf-8-sig'))
        source = Path(__file__).resolve().parents[1]/'experiments/cuda_projection/projection.cu'
        fault_path = fixture/'projection.dll'
        assert manifest.get('gpu_preview') is False
        assert hashlib.sha256(source.read_bytes()).hexdigest() == manifest['source_sha256'].lower()
        assert hashlib.sha256(fault_path.read_bytes()).hexdigest() == manifest['dll_sha256'].lower()
        # Explicit trusted local build, never a fixture accepted by the app loader.
        fault_dll = ctypes.CDLL(str(fault_path))
        inject = fault_dll.projection_create_injected
        inject.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_int, ctypes.c_int, ctypes.c_int]
        inject.restype = ctypes.c_int
        for stage in range(1, 7):
            handle = ctypes.c_void_p()
            assert inject(ctypes.byref(handle), 128, 64, stage) != 0
            assert handle.value is None
        report.update(status='passed', cycles=20, exact_comparisons=60, allocation_failure_stages=6, fault_fixture_source=manifest['source_sha256'],
                      fault_fixture_dll=manifest['dll_sha256'], production_fault_export=False)
    finally:
        (args.output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
