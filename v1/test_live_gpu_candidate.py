"""Matched real-engine GPU candidate parity and separate timing windows."""

import argparse
import json
import time
from pathlib import Path
import cv2
import numpy as np
from screento3d_app.desktop_jobs import BUNDLE
from screento3d_app.resources import configure_resource_root


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    configure_resource_root(BUNDLE)
    from screento3d_app.trt_backend import DepthEngine
    from screento3d_app.pipeline import StereoSynthesizer, preprocess
    from screento3d_app.live_projection import LiveProjection
    from screento3d_app.live_gpu_candidate import LiveGpuCandidate
    from screento3d_app.live_policy import resolve_live

    rows = []
    with DepthEngine() as engine:
        for width, height in [(320, 180), (1920, 1080)]:
            y, x = np.indices((height, width))
            base = np.stack((x % 256, y % 256, (x + y) % 256), -1).astype(np.uint8)
            for mode in ("performance", "balanced", "video-quality"):
                policy = resolve_live(mode)
                with (
                    LiveProjection(width, height) as projection,
                    LiveGpuCandidate(width, height, policy, engine) as gpu,
                ):
                    aligned_ref = []

                    def pair(frame, depth, shift, **kwargs):
                        aligned_ref[:] = [depth.copy()]
                        return projection.project_pair(frame, depth, shift, **kwargs)

                    reference = StereoSynthesizer(
                        width, height, policy, projection, paired_projection=pair
                    )
                    for index in range(4):
                        frame = np.roll(base, index * 3, axis=1)
                        if index == 3:
                            frame = 255 - frame
                        tensor = preprocess(frame)
                        raw = engine.infer(tensor)
                        expected = reference.render(frame, raw)
                        actual, aligned = gpu.render(
                            frame, gpu.infer(frame), diagnostic=True
                        )
                        error = np.abs(aligned - aligned_ref[0])
                        pixel = np.abs(
                            actual.astype(np.int16) - expected.astype(np.int16)
                        )
                        row = dict(
                            size=[width, height],
                            mode=mode,
                            frame=index,
                            depth_mae=float(error.mean()),
                            depth_max=float(error.max()),
                            rgb_mae=float(pixel.mean()),
                            rgb_changed_fraction=float(
                                np.mean(np.any(pixel != 0, axis=2))
                            ),
                        )
                        rows.append(row)
                        print(json.dumps(row), flush=True)
                        if width == 1920 and index == 2:
                            cv2.imwrite(
                                str(args.output / f"{mode}-reference.png"),
                                cv2.cvtColor(expected, cv2.COLOR_RGB2BGR),
                            )
                            cv2.imwrite(
                                str(args.output / f"{mode}-candidate.png"),
                                cv2.cvtColor(actual, cv2.COLOR_RGB2BGR),
                            )
                    timings = {"reference": [], "candidate": []}
                    for repeat in range(6):
                        for key in timings:
                            start = time.perf_counter()
                            for index in range(10):
                                frame = np.roll(base, index * 3, axis=1)
                                tensor = preprocess(frame)
                                if key == "reference":
                                    reference.render(frame, engine.infer(tensor))
                                else:
                                    gpu.render(frame, gpu.infer(frame))
                            elapsed = (time.perf_counter() - start) * 100
                            if repeat:
                                timings[key].append(elapsed)
                    rows.append(
                        dict(
                            size=[width, height],
                            mode=mode,
                            ten_frame_mean_ms=timings,
                            h2d=gpu.h2d,
                            d2h=gpu.d2h,
                            syncs=gpu.syncs,
                            cpu_refinements=gpu.cpu_refinements,
                        )
                    )
                    (args.output / "report.json").write_text(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
