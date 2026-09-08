"""Exact synthetic owner-map oracle and isolated CUDA time; not output fps."""

import ctypes as ct
import hashlib
import json
from pathlib import Path

import numpy as np


def oracle(rgb, owners):
    height, width = owners.shape
    result = np.empty_like(rgb)
    pixels = rgb.reshape(-1, 3)
    for y in range(height):
        valid = np.flatnonzero(owners[y])
        if not len(valid):
            result[y] = rgb[y]
            continue
        for x in range(width):
            rank = np.searchsorted(valid, x)
            if rank < len(valid) and valid[rank] == x:
                chosen = x
            else:
                left = int(valid[rank - 1]) if rank else -1
                right = int(valid[rank]) if rank < len(valid) else width
                chosen = left
                if left < 0 or (
                    right < width
                    and (int(owners[y, right]) >> 32) < (int(owners[y, left]) >> 32)
                ):
                    chosen = right
            result[y, x] = pixels[int(owners[y, chosen]) & 0xFFFFFFFF]
    return result


def main():
    from depthsbs_app.resources import prepare_dll_search_path

    prepare_dll_search_path()
    path = Path("out/live-parallel-projection/probe/resolve_probe.dll").resolve()
    dll = ct.CDLL(str(path))
    dll.probe_resolve.argtypes = [ct.c_void_p] * 3 + [ct.c_int] * 4 + [ct.c_void_p]
    rng = np.random.default_rng(5313)

    def run(rgb, owners, parallel, repeats):
        out = np.empty_like(rgb)
        times = np.zeros(repeats, np.float32)
        h, w = owners.shape
        code = dll.probe_resolve(
            rgb.ctypes.data,
            owners.ctypes.data,
            out.ctypes.data,
            w,
            h,
            parallel,
            repeats,
            times.ctypes.data,
        )
        assert code == 0, code
        return out, times.tolist()

    cases = []
    widths = (
        1,
        2,
        3,
        15,
        16,
        31,
        32,
        33,
        255,
        256,
        257,
        1023,
        1024,
        1025,
        1919,
        1920,
        2047,
        2048,
        2049,
        3840,
        4095,
        4096,
    )
    for width in widths:
        height = 7
        rgb = rng.integers(0, 256, (height, width, 3), dtype=np.uint8)
        for pattern in ("empty", "full", "leading", "trailing", "tie", "random"):
            source = rng.integers(0, width * height, (height, width), dtype=np.uint64)
            depths = rng.integers(1, 65537, (height, width), dtype=np.uint64)
            mask = np.ones((height, width), bool)
            if pattern == "empty":
                mask[:] = False
            elif pattern == "leading":
                mask[:, : width - 1] = False
            elif pattern == "trailing":
                mask[:, 1:] = False
            elif pattern == "tie":
                mask[:, 1:-1] = False
                depths[:] = 32768
            elif pattern == "random":
                mask = rng.random((height, width)) < 0.3
            owners = np.where(mask, (depths << np.uint64(32)) | source, 0)
            expected = oracle(rgb, owners)
            a, _ = run(rgb, owners, 0, 1)
            b, _ = run(rgb, owners, 1, 1)
            assert np.array_equal(a, expected), (width, pattern, "serial")
            assert np.array_equal(b, expected), (width, pattern, "parallel")
            cases.append(dict(width=width, height=height, pattern=pattern, exact=True))
    timings = []
    for width, height in ((1920, 1080), (3840, 2160)):
        rgb = rng.integers(0, 256, (height, width, 3), dtype=np.uint8)
        source = np.arange(width * height, dtype=np.uint64).reshape(height, width)
        for pattern in ("full", "holes", "empty", "long-hole"):
            owners = (np.uint64(32768) << np.uint64(32)) | source
            if pattern == "holes":
                owners[:, ::5] = 0
            elif pattern == "empty":
                owners[:] = 0
            elif pattern == "long-hole":
                owners[:, 1:-1] = 0
            # Alternate order across fixtures; both paths have three warmups.
            results = {}
            for parallel in (0, 1) if len(timings) % 2 == 0 else (1, 0):
                results[parallel] = run(rgb, owners, parallel, 15)
            assert np.array_equal(results[0][0], results[1][0])
            timings.append(
                dict(
                    width=width,
                    height=height,
                    pattern=pattern,
                    exact=True,
                    serial_ms=results[0][1],
                    parallel_ms=results[1][1],
                    serial_median_ms=float(np.median(results[0][1])),
                    parallel_median_ms=float(np.median(results[1][1])),
                )
            )
    report = dict(
        cases=cases,
        timings=timings,
        dll_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        note="Synthetic isolated resolve GPU intervals, not live fps or VR quality",
    )
    target = path.parent / "report.json"
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"{len(cases) + len(timings)} exact cases pass")
    for row in timings:
        print(
            row["width"],
            row["pattern"],
            row["serial_median_ms"],
            row["parallel_median_ms"],
        )


if __name__ == "__main__":
    main()
