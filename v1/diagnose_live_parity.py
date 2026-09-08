"""Stage isolation on pinned public footage; diagnostic copies excluded from fps."""

import argparse
import ctypes as ct
import json
from dataclasses import replace
from pathlib import Path
import cv2
import numpy as np
from public_test_media import prepare, PublicFrames
from depthsbs_app.desktop_jobs import BUNDLE
from depthsbs_app.resources import configure_resource_root


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scene", default="OfficeWalk")
    parser.add_argument("--frames", type=int, default=180)
    parser.add_argument("--transition", type=float, default=0.008)
    parser.add_argument(
        "--mode",
        default="balanced",
        choices=("performance", "balanced", "video-quality"),
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    prepare()
    configure_resource_root(BUNDLE)
    from depthsbs_app.trt_backend import DepthEngine, _cuda, cudart
    from depthsbs_app.pipeline import StereoSynthesizer, preprocess
    from depthsbs_app.live_gpu_candidate import LiveGpuCandidate
    from depthsbs_app.live_policy import resolve_live
    from depthsbs_app.stereo import guide_depth, color_change

    policy = replace(resolve_live(args.mode), temporal_depth_transition=args.transition)
    rows = []
    with DepthEngine() as engine, LiveGpuCandidate(1920, 1080, policy, engine) as gpu:
        ref = StereoSynthesizer(1920, 1080, policy)
        # The projection is irrelevant to stage attribution; avoid CPU splatting.
        ref.project_pair = lambda frame, *a, **k: (frame, frame)
        gpu.dll.live_snapshot.argtypes = [ct.c_void_p] * 4
        previous_gpu = None
        for index, frame in enumerate(PublicFrames(args.scene, args.frames)):
            raw = engine.infer(preprocess(frame)).copy()
            prior = ref.smoothed_depth
            old_frame = ref.previous_frame
            reset = prior is None or ref.is_scene_cut(frame)
            ref.render(frame, raw)
            token = gpu.infer(frame)
            device_raw = np.empty_like(raw)
            _cuda(
                cudart.cudaMemcpyAsync(
                    device_raw.ctypes.data,
                    token.pointer,
                    raw.nbytes,
                    cudart.cudaMemcpyKind.cudaMemcpyDeviceToHost,
                    engine.stream,
                )
            )
            actual, aligned = gpu.render(frame, token, diagnostic=True)
            normalized = np.empty((1080, 1920), np.float32)
            smooth = np.empty_like(normalized)
            bounds = np.empty(2, np.float64)
            gpu._check(
                gpu.dll.live_snapshot(
                    gpu.handle,
                    normalized.ctypes.data,
                    smooth.ctypes.data,
                    bounds.ctypes.data,
                )
            )
            resized = cv2.resize(raw[0], (1920, 1080), interpolation=cv2.INTER_CUBIC)
            reference_normalized = np.clip(
                (resized - ref.low) / max(ref.high - ref.low, 1e-6), 0, 1
            )
            row = dict(
                frame=index,
                reset=reset,
                raw_max=float(np.max(np.abs(raw - device_raw))),
                bounds_max=float(np.max(np.abs(bounds - [ref.low, ref.high]))),
                normalized_max=float(np.max(np.abs(normalized - reference_normalized))),
                normalized_mae=float(
                    np.mean(np.abs(normalized - reference_normalized))
                ),
                temporal_max=float(np.max(np.abs(smooth - ref.smoothed_depth))),
                temporal_mae=float(np.mean(np.abs(smooth - ref.smoothed_depth))),
                guide_only_max=float(
                    np.max(
                        np.abs(
                            aligned
                            - guide_depth(
                                frame, smooth, radius=policy.depth_guide_radius
                            )
                        )
                    )
                ),
                final_max=float(
                    np.max(
                        np.abs(
                            aligned
                            - guide_depth(
                                frame,
                                ref.smoothed_depth,
                                radius=policy.depth_guide_radius,
                            )
                        )
                    )
                ),
            )
            if not reset:
                changed = (
                    cv2.dilate(
                        (
                            color_change(frame, old_frame)
                            > policy.temporal_color_threshold
                        ).astype(np.uint8),
                        np.ones((7, 7), np.uint8),
                    )
                    != 0
                )
                ref_mask = (
                    np.abs(reference_normalized - prior)
                    > policy.temporal_depth_threshold
                )
                gpu_mask = (
                    np.abs(normalized - previous_gpu) > policy.temporal_depth_threshold
                )
                mismatch = (ref_mask != gpu_mask) & ~changed
                row["threshold_mismatch"] = int(mismatch.sum())
                if mismatch.any():
                    y, x = np.argwhere(mismatch)[0]
                    row["first_mismatch"] = dict(
                        x=int(x),
                        y=int(y),
                        reference=float(reference_normalized[y, x] - prior[y, x]),
                        gpu=float(normalized[y, x] - previous_gpu[y, x]),
                    )
            previous_gpu = smooth.copy()
            rows.append(row)
            if index % 30 == 0 or index == 186 or row.get("threshold_mismatch", 0):
                print(json.dumps(row), flush=True)
        (args.output / "report.json").write_text(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
