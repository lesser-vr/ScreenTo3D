"""Exact paired GPU output parity and explicit transfer-count validation."""

import json
import time
from pathlib import Path
import numpy as np

from screento3d_app.live_projection import LiveProjection
from screento3d_app.local_projection import factory


def main():
    rows = []
    random = np.random.default_rng(20260905)
    for width, height in ((64, 48), (720, 480), (1920, 1080)):
        frame = random.integers(0, 256, (height, width, 3), dtype=np.uint8)
        depth = random.random((height, width), dtype=np.float32)
        shift = (depth - 0.5) * width * 0.02
        with (
            factory(width, height) as reference,
            LiveProjection(width, height) as paired,
        ):
            for coverage in (False, True):
                left = reference.project(frame, depth, shift, coverage)
                right = reference.project(frame, depth, -shift, coverage)
                started = time.perf_counter()
                actual = paired.project_pair(frame, depth, shift, coverage)
                elapsed = time.perf_counter() - started
                assert np.array_equal(left, actual[0]) and np.array_equal(
                    right, actual[1]
                )
                rows.append(
                    dict(
                        width=width,
                        height=height,
                        coverage=coverage,
                        exact=True,
                        host_to_host_pair_ms=elapsed * 1000,
                    )
                )
            metrics = paired.telemetry()
            assert metrics["h2d_bytes"] == 2 * width * height * 11
            assert metrics["stream_synchronizations"] == 2
            try:
                paired.project_pair(frame, depth, shift[:, :-1])
            except ValueError:
                pass
            else:
                raise AssertionError("invalid shape accepted")
        try:
            paired.project_pair(frame, depth, shift)
        except RuntimeError:
            pass
        else:
            raise AssertionError("use after close accepted")
    output = Path("out/live-sbs/paired-parity.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            dict(
                cases=rows,
                h2d_reduction_vs_two_eye_calls=0.5,
                note="Isolated parity, not full-pipeline speedup",
            ),
            indent=2,
        )
    )
    print(output.read_text())


if __name__ == "__main__":
    main()
