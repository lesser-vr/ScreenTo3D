"""Bounded matched 1080p CPU attribution; not live output throughput."""

import cProfile
import hashlib
import io
import json
import pstats
import time
from pathlib import Path

import cv2
import numpy as np
from depthsbs_app.desktop_jobs import BUNDLE
from depthsbs_app.resources import configure_resource_root


def main():
    configure_resource_root(BUNDLE)
    from depthsbs_app.trt_backend import DepthEngine
    from depthsbs_app.pipeline import StereoSynthesizer, preprocess
    from depthsbs_app.live_projection import LiveProjection
    from depthsbs_app.live_policy import resolve_live

    out = Path("out/live-gpu-speed/baseline")
    out.mkdir(parents=True, exist_ok=False)
    y, x = np.indices((1080, 1920))
    frame = np.stack(((x % 256), (y % 256), ((x + y) % 256)), -1).astype(np.uint8)
    profiler = cProfile.Profile()
    rows = []
    with DepthEngine() as engine, LiveProjection(1920, 1080) as projection:
        synth = StereoSynthesizer(
            1920,
            1080,
            resolve_live("balanced"),
            projection,
            paired_projection=projection.project_pair,
        )
        for index in range(66):
            current = np.roll(frame, index * 3, axis=1)
            if index == 6:
                profiler.enable()
            start = time.perf_counter_ns()
            tensor = preprocess(current)
            prep = time.perf_counter_ns()
            depth = engine.infer(tensor)
            infer = time.perf_counter_ns()
            result = synth.render(current, depth)
            end = time.perf_counter_ns()
            if index >= 6:
                rows.append(
                    dict(
                        preprocess_ms=(prep - start) / 1e6,
                        depth_ms=(infer - prep) / 1e6,
                        stereo_ms=(end - infer) / 1e6,
                        total_ms=(end - start) / 1e6,
                    )
                )
        profiler.disable()
        telemetry = dict(engine=engine.telemetry(), projection=projection.telemetry())
    text = io.StringIO()
    pstats.Stats(profiler, stream=text).sort_stats("tottime").print_stats(45)
    (out / "profile.txt").write_text(text.getvalue())
    profiler.dump_stats(str(out / "profile.pstats"))
    report = dict(
        rows=rows,
        telemetry=telemetry,
        source_sha256=hashlib.sha256(frame).hexdigest(),
        median_ms={key: float(np.median([r[key] for r in rows])) for key in rows[0]},
        note="CPU cProfile perturbs timing; 60 matched steady temporal frames, excludes WGC/Qt",
    )
    (out / "report.json").write_text(json.dumps(report, indent=2))
    cv2.imwrite(str(out / "generated-sbs.png"), cv2.cvtColor(result, cv2.COLOR_RGB2BGR))
    print(json.dumps(report["median_ms"]))
    print(text.getvalue())


if __name__ == "__main__":
    main()
