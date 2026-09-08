"""Compare the standalone public worker's postprocess wrapper to the pinned app."""

import argparse
import json
from pathlib import Path

import numpy as np

from depthsbs_app.desktop_jobs import BUNDLE
from depthsbs_app.resources import configure_resource_root
from depthsbs_app.live_gpu_candidate import LiveGpuCandidate
from depthsbs_app.live_policy import resolve_live
from public_test_media import PublicFrames, SOURCES
from texture_projection_oracle import (
    TextureProjectionOracle,
    PUBLISH_SHA256,
    POOL_SHA256,
)
from texture_public_worker import publish_frame


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pool", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    configure_resource_root(BUNDLE)
    from depthsbs_app.trt_backend import DepthEngine

    synthetic = []
    for index in range(6):
        frame = np.full((180, 320, 3), 220, np.uint8)
        frame[20:160, 80 + index * 4 : 140 + index * 4] = (20, 60, 100)
        if index == 4:
            frame = 255 - frame
        synthetic.append(frame)
    rows = []
    clears = 0
    with DepthEngine() as engine:
        for name, frames in [(name, PublicFrames(name, 12)) for name in SOURCES] + [
            ("flat-cut", synthetic)
        ]:
            height, width = frames[0].shape[:2]
            for mode in ("performance", "balanced", "video-quality"):
                policy = resolve_live(mode)
                with (
                    LiveGpuCandidate(width, height, policy, engine) as reference,
                    LiveGpuCandidate(width, height, policy, engine) as worker,
                    TextureProjectionOracle(
                        worker, publish=True, pool=args.pool
                    ) as surface,
                ):
                    for index, frame in enumerate(frames):
                        if index == 6:
                            reference.reset()
                            worker.reset()
                        expected = reference.render(frame, reference.infer(frame))
                        slot = index % 2
                        publish_frame(worker, surface, frame, slot, False)
                        surface._check(
                            surface.dll.live_texture_readback(
                                surface.handle, slot, surface.output.ctypes.data
                            )
                        )
                        exact = bool(
                            np.array_equal(surface.output[:, :, :3], expected)
                            and np.all(surface.output[:, :, 3] == 255)
                        )
                        rows.append(
                            dict(scene=name, mode=mode, frame=index, exact=exact)
                        )
                        assert exact, rows[-1]
                        if index == 2:
                            publish_frame(worker, surface, None, slot, True)
                            surface._check(
                                surface.dll.live_texture_readback(
                                    surface.handle, slot, surface.output.ctypes.data
                                )
                            )
                            assert np.all(surface.output[:, :, :3] == 0) and np.all(
                                surface.output[:, :, 3] == 255
                            )
                            clears += 1
                    print(
                        json.dumps(dict(scene=name, mode=mode, passed=True)), flush=True
                    )
    report = dict(
        passed=True,
        cases=rows,
        exact_count=len(rows),
        clear_count=clears,
        publish_dll_sha256=POOL_SHA256 if args.pool else PUBLISH_SHA256,
        scope="Short actual worker wrapper parity and clear/reset; not a full live pipeline benchmark",
    )
    (args.output / "report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}))


if __name__ == "__main__":
    main()
