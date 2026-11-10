"""Compare the production CUDA packing kernel against the CPU packing contract."""
import argparse
import ctypes as ct
import json
from pathlib import Path
import numpy as np
import torch
from depthsbs_app.stereo_layout import LAYOUTS, pack
from depthsbs_app.vfg_renderer import BridgePool


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    stream = torch.cuda.Stream()
    rows = []
    for width, height in ((17, 19), (1920, 1080), (3840, 2160)):
        rng = np.random.default_rng(17)
        frame = rng.integers(0, 256, (height, width * 2, 4), dtype=np.uint8)
        with torch.cuda.stream(stream):
            gpu = torch.as_tensor(frame, device="cuda")
        stream.synchronize()
        for layout in LAYOUTS:
            with BridgePool(width, height, diagnostic=True, layout=layout) as pool:
                dll = pool.dll
                dll.vfg_publish.argtypes = [ct.c_void_p] * 2 + [ct.c_int] * 3 + [ct.c_void_p]
                pool.check(dll.vfg_publish(pool.handle, gpu.data_ptr(), width * 2, height, 0, stream.cuda_stream))
                actual = np.empty((pool.height, pool.width, 4), np.uint8)
                pool.check(dll.live_pool_readback(pool.handle, 0, actual.ctypes.data))
                expected = pack(frame, layout)
                np.testing.assert_array_equal(actual, expected)
                rows.append(dict(layout=layout, source=[width, height],
                                 output=[pool.width, pool.height], exact=True))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"PASS: {len(rows)} GPU/CPU exact comparisons including odd dimensions and 4K")


if __name__ == "__main__":
    main()
