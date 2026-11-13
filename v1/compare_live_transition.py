"""Old/new live temporal behavior review using public OfficeWalk, not a fps test."""

import argparse
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import cv2
import numpy as np
from public_test_media import prepare, PublicFrames
from screento3d_app.desktop_jobs import BUNDLE
from screento3d_app.resources import configure_resource_root


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    sources = prepare()
    configure_resource_root(BUNDLE)
    from screento3d_app.trt_backend import DepthEngine
    from screento3d_app.live_projection import LiveProjection
    from screento3d_app.pipeline import StereoSynthesizer, preprocess
    from screento3d_app.live_policy import resolve_live

    policy = resolve_live("balanced")
    command = [
        str(BUNDLE / "ffmpeg/ffmpeg.exe"),
        "-v",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        "1920x1080",
        "-r",
        "60",
        "-i",
        "pipe:0",
        "-an",
        "-c:v",
        "libx264",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        str(args.output / "old-new-OfficeWalk.mp4"),
    ]
    encoder = subprocess.Popen(
        command, stdin=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW
    )
    rows = []
    try:
        with DepthEngine() as engine, LiveProjection(1920, 1080) as projection:
            old = StereoSynthesizer(
                1920,
                1080,
                replace(policy, temporal_depth_transition=0),
                projection,
                paired_projection=projection.project_pair,
            )
            new = StereoSynthesizer(
                1920,
                1080,
                policy,
                projection,
                paired_projection=projection.project_pair,
            )
            for index, frame in enumerate(PublicFrames("OfficeWalk", 180)):
                raw = engine.infer(preprocess(frame))
                before = old.render(frame, raw)
                after = new.render(frame, raw)
                diff = np.abs(after.astype(np.int16) - before.astype(np.int16))
                rows.append(
                    dict(
                        frame=index,
                        rgb_mae=float(diff.mean()),
                        changed_fraction=float(np.any(diff != 0, axis=2).mean()),
                    )
                )
                stacked = np.concatenate(
                    [
                        cv2.resize(im, (1920, 540), interpolation=cv2.INTER_AREA)
                        for im in (before, after)
                    ]
                )
                for y, label in (
                    (30, "OLD LIVE TEMPORAL"),
                    (570, "NEW CONTINUOUS LIVE TEMPORAL"),
                ):
                    cv2.rectangle(stacked, (0, y - 30), (650, y + 10), (0, 0, 0), -1)
                    cv2.putText(
                        stacked,
                        label,
                        (12, y),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.8,
                        (255, 255, 255),
                        2,
                    )
                encoder.stdin.write(stacked.tobytes())
                if index in (92, 164, 169):
                    cv2.imwrite(
                        str(args.output / f"comparison-{index}.png"),
                        cv2.cvtColor(stacked, cv2.COLOR_RGB2BGR),
                    )
        encoder.stdin.close()
        if encoder.wait(timeout=60):
            raise RuntimeError("Review encoder failed")
    finally:
        if encoder.poll() is None:
            encoder.kill()
            encoder.wait(timeout=10)
    (args.output / "report.json").write_text(
        json.dumps(
            dict(
                public_sources=sources,
                rows=rows,
                note="Old/new live policy comparison; not GPU/reference parity or quality approval",
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
