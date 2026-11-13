"""Old/new percentile path: exact complete stereo pixels, separate microtiming."""

import json
import time
from pathlib import Path
from unittest.mock import patch
import numpy as np
from screento3d_app.pipeline import StereoSynthesizer
from screento3d_app.live_policy import LIVE_MODES, resolve_live


def main():
    rng = np.random.default_rng(9123)
    original = np.percentile

    def previous(a, q, *args, **kwargs):
        if isinstance(q, list) and q == [2.0, 98.0]:
            return np.asarray([original(a, k, *args, **kwargs) for k in q])
        return original(a, q, *args, **kwargs)

    cases = []
    for mode in LIVE_MODES:
        old = StereoSynthesizer(320, 180, resolve_live(mode))
        new = StereoSynthesizer(320, 180, resolve_live(mode))
        for index in range(4):
            frame = rng.integers(0, 256, (180, 320, 3), dtype=np.uint8)
            depth = rng.random((1, 518, 518), dtype=np.float32)
            with patch("screento3d_app.pipeline.np.percentile", side_effect=previous):
                reference = old.render(frame, depth)
            actual = new.render(frame, depth)
            assert np.array_equal(reference, actual), (mode, index)
            cases.append(dict(mode=mode, frame=index, exact=True))
    array = rng.random((1080, 1920), dtype=np.float32)
    times = {"old": [], "combined": []}
    for _ in range(6):
        for key, fn in [
            ("old", lambda: previous(array, [2.0, 98.0])),
            ("combined", lambda: original(array, [2.0, 98.0]).astype(array.dtype)),
        ]:
            start = time.perf_counter()
            fn()
            times[key].append((time.perf_counter() - start) * 1000)
    for key in times:
        times[key] = times[key][1:]
    report = dict(
        cases=cases,
        percentile_only_ms=times,
        note="CPU microtiming only; not full-pipeline speedup",
    )
    target = Path("out/live-modes/quantile-parity.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2))
    print(json.dumps(report))


if __name__ == "__main__":
    main()
