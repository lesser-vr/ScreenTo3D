"""Attribute post history and real oVDA inference skipping for 1:2 cadence."""

import argparse
from contextlib import ExitStack
import hashlib
import heapq
import json
from pathlib import Path
import statistics
import subprocess

import cv2
import numpy as np

from evaluate_ovda_nvof_cadence import (
    POST_DLL,
    THRESHOLDS,
    cadence_decision,
    combined,
    label,
    output_metrics,
    percentile,
    scene_flags,
    temporal_change,
)
from nvof_device_warp import NvofDeviceWarp, checked_manifest
from public_test_media import ATTRIBUTION, BUNDLE, PublicFrames
from test_ovda_device_post import SourcePost, create_engine, engine_classes
from test_ovda_nvof import CLIPS, normalize

ROOT = Path(__file__).resolve().parents[1]
PATH_NAMES = (
    "scheduled_all_infer",
    "actual_continuous",
    "actual_reset_before_fresh",
    "actual_dual_source",
    "actual_held_continuous",
)


def should_infer(kind):
    if kind not in ("fresh", "cut-fresh", "warped"):
        raise ValueError("Unknown cadence kind")
    return kind != "warped"


def reset_before_fresh(cut, kind, previous_kind):
    return bool(cut or (should_infer(kind) and previous_kind == "warped"))


def host_depth(token):
    token.validate()
    token.owner.stream.synchronize()
    value = token.tensor.detach().cpu().numpy()[0]
    return np.ascontiguousarray(value, dtype=np.float32)


def as_source_depth(value):
    value = np.ascontiguousarray(value, dtype=np.float32)
    if value.ndim != 2 or not np.isfinite(value).all():
        raise ValueError("Invalid diagnostic depth")
    return value[None]


def path_summary(rows, name):
    values = [row["outputs"][name] for row in rows]
    fresh = [value for row, value in zip(rows, values) if should_infer(row["kind"])]
    warped = [
        value for row, value in zip(rows, values) if not should_infer(row["kind"])
    ]
    temporal = [value["temporal_change_error"] for value in values[1:]]
    result = {
        "mean_sbs_mae": statistics.mean(value["sbs_mae"] for value in values),
        "mean_fresh_sbs_mae": statistics.mean(value["sbs_mae"] for value in fresh),
        "mean_warped_sbs_mae": statistics.mean(value["sbs_mae"] for value in warped),
        "p95_frame_sbs_mae": percentile([value["sbs_mae"] for value in values], 95),
        "maximum_frame_sbs_mae": max(value["sbs_mae"] for value in values),
        "mean_edge_sbs_mae": statistics.mean(value["edge_sbs_mae"] for value in values),
        "mean_channels_over_8_fraction": statistics.mean(
            value["channels_over_8_fraction"] for value in values
        ),
        "p95_temporal_change_error": percentile(temporal, 95),
    }
    result["output_gate_checks"] = {
        "mean_sbs_mae": result["mean_sbs_mae"] <= THRESHOLDS["maximum_mean_sbs_mae"],
        "p95_frame_sbs_mae": result["p95_frame_sbs_mae"]
        <= THRESHOLDS["maximum_p95_frame_sbs_mae"],
        "mean_edge_sbs_mae": result["mean_edge_sbs_mae"]
        <= THRESHOLDS["maximum_mean_edge_sbs_mae"],
        "large_channel_error_fraction": result["mean_channels_over_8_fraction"]
        <= THRESHOLDS["maximum_mean_channels_over_8_fraction"],
        "temporal_change_error": result["p95_temporal_change_error"]
        <= THRESHOLDS["maximum_p95_temporal_change_error"],
    }
    result["output_gate_passed"] = all(result["output_gate_checks"].values())
    return result


def summarize(rows, reference_telemetry, candidate_telemetry):
    warped = [row for row in rows if not should_infer(row["kind"])]
    fresh = [row for row in rows if should_infer(row["kind"])]
    actual_warp = statistics.mean(row["actual_depth_mae"] for row in warped)
    actual_hold = statistics.mean(row["actual_held_depth_mae"] for row in warped)
    scheduled_warp = statistics.mean(row["scheduled_depth_mae"] for row in warped)
    scheduled_hold = statistics.mean(row["scheduled_held_depth_mae"] for row in warped)
    paths = {name: path_summary(rows, name) for name in PATH_NAMES}
    selectable = (
        "actual_continuous",
        "actual_reset_before_fresh",
        "actual_dual_source",
    )
    result = {
        "frames": len(rows),
        "reference_inferences": reference_telemetry["completed_inferences"],
        "candidate_inferences": candidate_telemetry["completed_inferences"],
        "expected_candidate_inferences": len(fresh),
        "inference_reduction_fraction": 1
        - candidate_telemetry["completed_inferences"]
        / reference_telemetry["completed_inferences"],
        "mean_fresh_recurrent_depth_mae": statistics.mean(
            row["actual_depth_mae"] for row in fresh
        ),
        "maximum_fresh_recurrent_depth_mae": max(
            row["actual_depth_mae"] for row in fresh
        ),
        "mean_actual_warped_depth_mae": actual_warp,
        "mean_actual_held_depth_mae": actual_hold,
        "actual_warp_to_hold_depth_ratio": actual_warp / actual_hold
        if actual_hold
        else None,
        "mean_scheduled_warped_depth_mae": scheduled_warp,
        "mean_scheduled_held_depth_mae": scheduled_hold,
        "scheduled_warp_to_hold_depth_ratio": scheduled_warp / scheduled_hold
        if scheduled_hold
        else None,
        "minimum_actual_warp_valid_fraction": min(
            row["actual_valid_fraction"] for row in warped
        ),
        "mean_actual_vs_scheduled_sbs_mae": statistics.mean(
            row["actual_vs_scheduled_sbs_mae"] for row in rows
        ),
        "mean_continuous_vs_dual_sbs_mae": statistics.mean(
            row["continuous_vs_dual_sbs_mae"] for row in rows
        ),
        "mean_fresh_continuous_vs_dual_sbs_mae": statistics.mean(
            row["continuous_vs_dual_sbs_mae"] for row in fresh
        ),
        "paths": paths,
    }
    result["checks"] = {
        "frame_count": len(rows) == 60,
        "actual_inference_count": (
            reference_telemetry["completed_inferences"] == 60
            and candidate_telemetry["completed_inferences"] == len(fresh)
        ),
        "ownership_cleanup": (
            not reference_telemetry["pending_device_depth"]
            and not candidate_telemetry["pending_device_depth"]
        ),
        "warp_valid_coverage": result["minimum_actual_warp_valid_fraction"]
        >= THRESHOLDS["minimum_warp_valid_fraction"],
        "actual_warp_not_worse_than_hold": result["actual_warp_to_hold_depth_ratio"]
        <= THRESHOLDS["maximum_depth_mae_ratio_to_fixed"],
        "one_history_policy_passes_output_gate": any(
            paths[name]["output_gate_passed"] for name in selectable
        ),
    }
    result["candidate_retained_for_confidence_experiment"] = all(
        result["checks"].values()
    )
    return result


def review_grid(reference, continuous, dual, index, kind, source_index):
    rows = []
    for eyes, name in (
        (reference, "full-rate reference"),
        (continuous, "actual-skip continuous"),
        (dual, "actual-skip dual-source"),
    ):
        cells = []
        for eye, side in zip(eyes, ("L", "R")):
            cell = cv2.resize(eye, (640, 360), interpolation=cv2.INTER_AREA)
            label(cell, f"{name} {side} f{index:02d} {kind} {source_index:02d}")
            cells.append(cell)
        rows.append(np.concatenate(cells, axis=1))
    return np.ascontiguousarray(np.concatenate(rows, axis=0))


class AttributionWriter:
    def __init__(self, path, fps=60):
        path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            str(BUNDLE / "ffmpeg/ffmpeg.exe"),
            "-v",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            "1280x1080",
            "-r",
            str(fps),
            "-i",
            "-",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ]
        self.process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stderr=subprocess.PIPE
        )

    def write(self, frame):
        if frame.shape != (1080, 1280, 3) or frame.dtype != np.uint8:
            raise ValueError("Invalid attribution review frame")
        self.process.stdin.write(frame.tobytes())

    def close(self):
        if self.process is None:
            return
        process, self.process = self.process, None
        process.stdin.close()
        error = process.stderr.read().decode("utf-8", errors="replace")
        code = process.wait()
        if code:
            raise RuntimeError(f"Attribution review encode failed: {error.strip()}")

    def __enter__(self):
        return self

    def __exit__(self, kind, primary, tb):
        try:
            self.close()
        except Exception as error:
            if primary is None:
                raise
            primary.add_note(str(error))


def verify_attribution_video(path, expected_frames=60):
    path = Path(path)
    capture = cv2.VideoCapture(str(path))
    try:
        container_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        decoded_frames = 0
        while True:
            ok, _ = capture.read()
            if not ok:
                break
            decoded_frames += 1
    finally:
        capture.release()
    return {
        "passed": (
            container_frames == expected_frames
            and decoded_frames == expected_frames
            and (width, height) == (1280, 1080)
        ),
        "container_frame_count": container_frames,
        "decoded_frame_count": decoded_frames,
        "width": width,
        "height": height,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def evaluate_clip(name, DeviceEngine, policy, output_root):
    source = PublicFrames(name, 60)
    frames = [np.ascontiguousarray(frame) for frame in source]
    flags = scene_flags(frames, policy.scene_cut_threshold)
    height, width = frames[0].shape[:2]
    reference_engine = create_engine(DeviceEngine)
    candidate_engine = create_engine(DeviceEngine)
    rows = []
    worst = []
    last_fresh_index = None
    previous_kind = None
    last_reference_fresh = None
    last_candidate_fresh = None
    previous_outputs = {name: None for name in PATH_NAMES}
    dual_warp_reset_pending = True
    video_path = output_root / "review" / f"{name}.mp4"
    try:
        reference_engine.reset("start")
        candidate_engine.reset("start")
        with ExitStack() as stack:
            reference_warp = stack.enter_context(NvofDeviceWarp(width, height))
            candidate_warp = stack.enter_context(NvofDeviceWarp(width, height))
            posts = {
                "reference": stack.enter_context(
                    SourcePost(reference_engine, width, height, policy, POST_DLL)
                ),
                "scheduled_all_infer": stack.enter_context(
                    SourcePost(reference_engine, width, height, policy, POST_DLL)
                ),
                "actual_continuous": stack.enter_context(
                    SourcePost(candidate_engine, width, height, policy, POST_DLL)
                ),
                "actual_reset_before_fresh": stack.enter_context(
                    SourcePost(candidate_engine, width, height, policy, POST_DLL)
                ),
                "actual_fresh_source": stack.enter_context(
                    SourcePost(candidate_engine, width, height, policy, POST_DLL)
                ),
                "actual_warp_source": stack.enter_context(
                    SourcePost(candidate_engine, width, height, policy, POST_DLL)
                ),
                "actual_held_continuous": stack.enter_context(
                    SourcePost(candidate_engine, width, height, policy, POST_DLL)
                ),
            }
            writer = stack.enter_context(AttributionWriter(video_path))
            for index, (frame, cut) in enumerate(zip(frames, flags)):
                if cut and index:
                    reference_engine.reset("scene_cut")
                    candidate_engine.reset("scene_cut")
                    dual_warp_reset_pending = True
                kind, source_index = cadence_decision(
                    index,
                    cut,
                    last_fresh_index,
                )
                reference_token = reference_engine.infer_device(frame)
                candidate_token = None
                reference_warp_token = None
                candidate_warp_token = None
                try:
                    reference_depth = host_depth(reference_token)
                    if should_infer(kind):
                        candidate_token = candidate_engine.infer_device(frame)
                        _, scheduled_depth, _ = reference_warp.seed_pointer(
                            frame, reference_token, diagnostic=True
                        )
                        _, actual_depth, _ = candidate_warp.seed_pointer(
                            frame, candidate_token, diagnostic=True
                        )
                        scheduled_valid = np.ones((height, width), np.uint8)
                        actual_valid = np.ones((height, width), np.uint8)
                        last_reference_fresh = np.ascontiguousarray(scheduled_depth)
                        last_candidate_fresh = np.ascontiguousarray(actual_depth)
                        last_fresh_index = index
                    else:
                        (
                            reference_warp_token,
                            _,
                            scheduled_depth,
                            scheduled_valid,
                            _,
                        ) = reference_warp.warp(frame, diagnostic=True)
                        (
                            candidate_warp_token,
                            _,
                            actual_depth,
                            actual_valid,
                            _,
                        ) = candidate_warp.warp(frame, diagnostic=True)
                finally:
                    if reference_warp_token is not None:
                        reference_warp.complete(reference_warp_token, retain=False)
                    if candidate_warp_token is not None:
                        candidate_warp.complete(candidate_warp_token, retain=False)
                    if candidate_token is not None:
                        candidate_engine.complete_device(candidate_token)
                    reference_engine.complete_device(reference_token)

                if last_reference_fresh is None or last_candidate_fresh is None:
                    raise RuntimeError("Cadence did not establish fresh depth")
                reference_eyes = posts["reference"].render(
                    frame, as_source_depth(reference_depth), device=False, reset=cut
                )
                scheduled_eyes = posts["scheduled_all_infer"].render(
                    frame, as_source_depth(scheduled_depth), device=False, reset=cut
                )
                continuous_eyes = posts["actual_continuous"].render(
                    frame, as_source_depth(actual_depth), device=False, reset=cut
                )
                reset_eyes = posts["actual_reset_before_fresh"].render(
                    frame,
                    as_source_depth(actual_depth),
                    device=False,
                    reset=reset_before_fresh(cut, kind, previous_kind),
                )
                if should_infer(kind):
                    dual_eyes = posts["actual_fresh_source"].render(
                        frame, as_source_depth(actual_depth), device=False, reset=cut
                    )
                    if cut:
                        dual_warp_reset_pending = True
                else:
                    dual_eyes = posts["actual_warp_source"].render(
                        frame,
                        as_source_depth(actual_depth),
                        device=False,
                        reset=dual_warp_reset_pending,
                    )
                    dual_warp_reset_pending = False
                held_eyes = posts["actual_held_continuous"].render(
                    frame,
                    as_source_depth(last_candidate_fresh),
                    device=False,
                    reset=cut,
                )
                reference_sbs = combined(reference_eyes)
                output_frames = {
                    "scheduled_all_infer": combined(scheduled_eyes),
                    "actual_continuous": combined(continuous_eyes),
                    "actual_reset_before_fresh": combined(reset_eyes),
                    "actual_dual_source": combined(dual_eyes),
                    "actual_held_continuous": combined(held_eyes),
                }
                outputs = {}
                for path_name, output in output_frames.items():
                    metrics = output_metrics(reference_sbs, output)
                    metrics["temporal_change"] = temporal_change(
                        output, previous_outputs[path_name]
                    )
                    reference_change = temporal_change(
                        reference_sbs,
                        previous_outputs.get("reference"),
                    )
                    metrics["temporal_change_error"] = (
                        abs(metrics["temporal_change"] - reference_change)
                        if reference_change is not None
                        else None
                    )
                    outputs[path_name] = metrics
                    previous_outputs[path_name] = output
                previous_outputs["reference"] = reference_sbs
                reference_normalized = normalize(reference_depth)
                scheduled_normalized = normalize(scheduled_depth)
                actual_normalized = normalize(actual_depth)
                scheduled_mask = scheduled_valid != 0
                actual_mask = actual_valid != 0
                row = {
                    "frame": index,
                    "cut": bool(cut),
                    "kind": kind,
                    "source_depth_frame": source_index,
                    "candidate_inferred": should_infer(kind),
                    "scheduled_valid_fraction": float(scheduled_mask.mean()),
                    "actual_valid_fraction": float(actual_mask.mean()),
                    "scheduled_depth_mae": float(
                        np.abs(reference_normalized - scheduled_normalized)[
                            scheduled_mask
                        ].mean()
                    ),
                    "scheduled_held_depth_mae": float(
                        np.abs(reference_normalized - normalize(last_reference_fresh))[
                            scheduled_mask
                        ].mean()
                    ),
                    "actual_depth_mae": float(
                        np.abs(reference_normalized - actual_normalized)[
                            actual_mask
                        ].mean()
                    ),
                    "actual_held_depth_mae": float(
                        np.abs(reference_normalized - normalize(last_candidate_fresh))[
                            actual_mask
                        ].mean()
                    ),
                    "reset_before_fresh": reset_before_fresh(cut, kind, previous_kind),
                    "actual_vs_scheduled_sbs_mae": output_metrics(
                        output_frames["scheduled_all_infer"],
                        output_frames["actual_continuous"],
                    )["sbs_mae"],
                    "continuous_vs_dual_sbs_mae": output_metrics(
                        output_frames["actual_continuous"],
                        output_frames["actual_dual_source"],
                    )["sbs_mae"],
                    "outputs": outputs,
                }
                rows.append(row)
                review = review_grid(
                    reference_eyes,
                    continuous_eyes,
                    dual_eyes,
                    index,
                    kind,
                    source_index,
                )
                writer.write(review)
                item = (
                    outputs["actual_continuous"]["sbs_mae"],
                    index,
                    review.copy(),
                )
                if len(worst) < 3:
                    heapq.heappush(worst, item)
                elif item[:2] > worst[0][:2]:
                    heapq.heapreplace(worst, item)
                previous_kind = kind
        reference_telemetry = reference_engine.telemetry()
        candidate_telemetry = candidate_engine.telemetry()
    finally:
        reference_engine.close()
        candidate_engine.close()

    stills = []
    still_root = output_root / "stills"
    still_root.mkdir(parents=True, exist_ok=True)
    for error, index, image in sorted(worst, reverse=True):
        path = still_root / f"{name}-frame-{index:02d}.png"
        if not cv2.imwrite(str(path), cv2.cvtColor(image, cv2.COLOR_RGB2BGR)):
            raise RuntimeError("Attribution still write failed")
        stills.append(
            {
                "frame": index,
                "actual_continuous_sbs_mae": error,
                "path": str(path.resolve()),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    media = verify_attribution_video(video_path)
    summary = summarize(rows, reference_telemetry, candidate_telemetry)
    summary["media_passed"] = media["passed"] and len(stills) == 3
    summary["candidate_retained_for_confidence_experiment"] = (
        summary["candidate_retained_for_confidence_experiment"]
        and summary["media_passed"]
    )
    return {
        "input": str(source.path.resolve()),
        "input_sha256": hashlib.sha256(source.path.read_bytes()).hexdigest(),
        "scene_reset_indices": [index for index, cut in enumerate(flags) if cut],
        "rows": rows,
        "summary": summary,
        "review_video": {"path": str(video_path.resolve()), **media},
        "worst_stills": stills,
        "reference_engine": reference_telemetry,
        "candidate_engine": candidate_telemetry,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Fresh output directory required")
    args.output.mkdir(parents=True)
    report_path = args.output / "report.json"
    report = {
        "passed": False,
        "candidate_retained_for_confidence_experiment": False,
        "scheduler_authorized": False,
        "visual_review": "required",
        "scope": (
            "Actual 1:2 recurrent inference skipping and post-history attribution. "
            "Host diagnostic post copies and readbacks are included; this is not a "
            "runtime throughput, perceptual-equivalence, sustained, or VR claim."
        ),
        "attribution": ATTRIBUTION,
        "thresholds_reused_from_fixed_cadence_gate": THRESHOLDS,
        "warp_manifest": checked_manifest(),
        "clips": {},
    }

    def save():
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    save()
    _, DeviceEngine, _ = engine_classes()
    from screento3d_app.live_policy import resolve_live

    policy = resolve_live("video-quality")
    for name in CLIPS:
        report["clips"][name] = evaluate_clip(name, DeviceEngine, policy, args.output)
        save()
    report["candidate_retained_for_confidence_experiment"] = all(
        clip["summary"]["candidate_retained_for_confidence_experiment"]
        for clip in report["clips"].values()
    )
    report["passed"] = all(
        clip["summary"]["media_passed"]
        and clip["summary"]["checks"]["frame_count"]
        and clip["summary"]["checks"]["actual_inference_count"]
        and clip["summary"]["checks"]["ownership_cleanup"]
        for clip in report["clips"].values()
    )
    save()
    print(report_path.resolve())


if __name__ == "__main__":
    main()
