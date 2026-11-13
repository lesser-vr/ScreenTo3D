"""Owned-copy attribution only, never a live output throughput benchmark."""

import argparse
import ctypes
import json
import multiprocessing as mp
import time
from pathlib import Path
import numpy as np
from screento3d_app.owned_preview_image import copy_image, PreviewCopyPool


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    width, height = 3840, 1080
    storage = mp.get_context("spawn").RawArray(ctypes.c_ubyte, width * height * 4)
    source = np.frombuffer(storage, np.uint8)
    source[:] = np.arange(source.size, dtype=np.uint8)
    results = []
    for mode in ("qt", "numpy", "pool", "qt", "pool"):
        samples = []
        pool = PreviewCopyPool()
        result = None
        for index in range(110):
            began = time.perf_counter_ns()
            result = (
                pool.copy(storage, width, height)
                if mode == "pool"
                else copy_image(storage, width, height, mode)
            )
            if index >= 10:
                samples.append((time.perf_counter_ns() - began) / 1e6)
        assert np.array_equal(np.frombuffer(result.constBits(), np.uint8), source)
        source[0] ^= 255
        assert np.frombuffer(result.constBits(), np.uint8)[0] != source[0]
        source[0] ^= 255
        results.append(
            dict(
                mode=mode,
                samples_ms=samples,
                median_ms=float(np.median(samples)),
                p95_ms=float(np.percentile(samples, 95)),
                exact_owned=True,
            )
        )
    (args.output / "report.json").write_text(json.dumps(results, indent=2))
    print(
        json.dumps([{k: v for k, v in r.items() if k != "samples_ms"} for r in results])
    )


if __name__ == "__main__":
    main()
