"""Evaluate full-rate oVDA against a fixed fresh/warped 1:2 depth cadence."""

import argparse
from contextlib import ExitStack
import hashlib
import heapq
import json
import os
from pathlib import Path
import statistics
import subprocess

import cv2
import numpy as np

from nvof_device_warp import NvofDeviceWarp, checked_manifest
from public_test_media import ATTRIBUTION, BUNDLE, PublicFrames
from test_ovda_device_post import SourcePost, create_engine, engine_classes
from test_ovda_nvof import CLIPS, normalize

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path("C:/TensorRT/TensorRT-11.2.1.2/bin")
POST_DLL = ROOT / "out/ovda-device-post-spike/live_depth.dll"
THRESHOLDS = {
    "minimum_warp_valid_fraction": 0.98,
    "maximum_depth_mae_ratio_to_fixed": 1.0,
    "maximum_mean_sbs_mae": 2 / 255,
    "maximum_p95_frame_sbs_mae": 3 / 255,
    "maximum_mean_edge_sbs_mae": 4 / 255,
    "maximum_mean_channels_over_8_fraction": 0.02,
    "maximum_p95_temporal_change_error": 3 / 255,
}


def cadence_decision(index, cut, last_fresh):
    if index < 0 or (last_fresh is not None and last_fresh >= index):
        raise ValueError("Invalid cadence identity")
    if index % 2 == 0:
        return "fresh", index
    if cut:
        return "cut-fresh", index
    if last_fresh is None:
        raise RuntimeError("Warped frame has no fresh source")
    return "warped", last_fresh


def scene_flags(frames, threshold):
    from screento3d_app.live_scene_history import LiveSceneHistory

    history = LiveSceneHistory(threshold)
    flags = []
    for index, frame in enumerate(frames):
        observation = history.inspect(frame)
        flags.append(index == 0 or observation.cut)
        history.commit(observation)
    return flags


def percentile(values, quantile):
    return float(np.percentile(np.asarray(values, np.float64), quantile))


def combined(eyes):
    return np.ascontiguousarray(np.concatenate(eyes, axis=1))


def output_metrics(reference, candidate):
    delta = np.abs(reference.astype(np.int16) - candidate.astype(np.int16))
    gray = cv2.cvtColor(reference, cv2.COLOR_RGB2GRAY)
    edges = cv2.dilate(
        cv2.Canny(gray, 60, 120), np.ones((5, 5), np.uint8)
    ).astype(bool)
    return {
        "sbs_mae": float(delta.mean() / 255),
        "sbs_p95_channel_error": float(np.percentile(delta, 95) / 255),
        "sbs_max_channel_error": int(delta.max()),
        "edge_sbs_mae": float(delta[edges].mean() / 255) if edges.any() else 0.0,
        "channels_over_8_fraction": float((delta > 8).mean()),
    }


def temporal_change(frame, previous):
    if previous is None:
        return None
    return float(
        np.abs(frame.astype(np.int16) - previous.astype(np.int16)).mean() / 255
    )


def label(image, text):
    cv2.putText(
        image,
        text,
        (22, 42),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (0, 0, 0),
        5,
        cv2.LINE_AA,
    )
    cv2.putText(
        image,
        text,
        (22, 42),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )


def review_frame(reference_eyes, candidate_eyes, index, kind, source_index):
    cells = []
    for eye, name in zip(reference_eyes, ("reference left", "reference right")):
        cell = cv2.resize(eye, (960, 540), interpolation=cv2.INTER_AREA)
        label(cell, f"{name}  frame {index:02d}")
        cells.append(cell)
    for eye, name in zip(candidate_eyes, ("candidate left", "candidate right")):
        cell = cv2.resize(eye, (960, 540), interpolation=cv2.INTER_AREA)
        label(cell, f"{name}  {kind} depth {source_index:02d}")
        cells.append(cell)
    return np.ascontiguousarray(
        np.concatenate(
            (np.concatenate(cells[:2], axis=1), np.concatenate(cells[2:], axis=1)),
            axis=0,
        )
    )


class ReviewWriter:
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
            "1920x1080",
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
        self.path = path
        self.process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stderr=subprocess.PIPE
        )

    def write(self, frame):
        if frame.shape != (1080, 1920, 3) or frame.dtype != np.uint8:
            raise ValueError("Invalid review frame")
        self.process.stdin.write(frame.tobytes())

    def close(self):
        if self.process is None:
            return
        process, self.process = self.process, None
        process.stdin.close()
        error = process.stderr.read().decode("utf-8", errors="replace")
        code = process.wait()
        if code:
            raise RuntimeError(f"Review encode failed: {error.strip()}")

    def __enter__(self):
        return self

    def __exit__(self, kind, primary, tb):
        try:
            self.close()
        except Exception as error:
            if primary is None:
                raise
            primary.add_note(str(error))


def verify_video(path, expected_frames=60):
    capture = cv2.VideoCapture(str(path))
    try:
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        decoded = 0
        while True:
            ok, _ = capture.read()
            if not ok:
                break
            decoded += 1
    finally:
        capture.release()
    passed = (
        frame_count == expected_frames
        and decoded == expected_frames
        and (width, height) == (1920, 1080)
    )
    return {
        "passed": passed,
        "container_frame_count": frame_count,
        "decoded_frame_count": decoded,
        "width": width,
        "height": height,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def summarize(rows):
    warped = [row for row in rows if row["candidate_kind"] == "warped"]
    fresh = [row for row in rows if row["candidate_kind"] != "warped"]
    temporal = [
        row["temporal_change_error"]
        for row in rows
        if row["temporal_change_error"] is not None
    ]
    warped_mae = statistics.mean(row["depth_mae"] for row in warped)
    fixed_mae = statistics.mean(row["fixed_prior_depth_mae"] for row in warped)
    summary = {
        "frames": len(rows),
        "scheduled_fresh_frames": sum(row["candidate_kind"] == "fresh" for row in rows),
        "cut_fresh_frames": sum(row["candidate_kind"] == "cut-fresh" for row in rows),
        "warped_frames": len(warped),
        "fresh_depth_exact_frames": sum(row["fresh_depth_exact"] is True for row in fresh),
        "minimum_warp_valid_fraction": min(row["valid_fraction"] for row in warped),
        "mean_warped_depth_mae": warped_mae,
        "mean_fixed_prior_depth_mae": fixed_mae,
        "depth_mae_ratio_to_fixed": warped_mae / fixed_mae if fixed_mae else None,
        "mean_sbs_mae": statistics.mean(row["sbs_mae"] for row in rows),
        "mean_fresh_sbs_mae": statistics.mean(row["sbs_mae"] for row in fresh),
        "mean_warped_sbs_mae": statistics.mean(row["sbs_mae"] for row in warped),
        "p95_frame_sbs_mae": percentile([row["sbs_mae"] for row in rows], 95),
        "maximum_frame_sbs_mae": max(row["sbs_mae"] for row in rows),
        "mean_edge_sbs_mae": statistics.mean(row["edge_sbs_mae"] for row in rows),
        "mean_fresh_edge_sbs_mae": statistics.mean(
            row["edge_sbs_mae"] for row in fresh
        ),
        "mean_warped_edge_sbs_mae": statistics.mean(
            row["edge_sbs_mae"] for row in warped
        ),
        "mean_channels_over_8_fraction": statistics.mean(
            row["channels_over_8_fraction"] for row in rows
        ),
        "p95_temporal_change_error": percentile(temporal, 95),
        "maximum_temporal_change_error": max(temporal),
        "all_identities_valid": all(
            row["reference_depth_frame"] == row["frame"]
            and (
                row["candidate_source_depth_frame"] == row["frame"]
                if row["candidate_kind"] != "warped"
                else row["candidate_source_depth_frame"] < row["frame"]
            )
            and not (row["cut"] and row["candidate_kind"] == "warped")
            for row in rows
        ),
    }
    checks = {
        "frame_and_identity_contract": (
            summary["frames"] == 60
            and summary["scheduled_fresh_frames"] == 30
            and summary["all_identities_valid"]
        ),
        "fresh_depth_exact": summary["fresh_depth_exact_frames"] == len(fresh),
        "warp_valid_coverage": summary["minimum_warp_valid_fraction"]
        >= THRESHOLDS["minimum_warp_valid_fraction"],
        "depth_not_worse_than_fixed": summary["depth_mae_ratio_to_fixed"]
        <= THRESHOLDS["maximum_depth_mae_ratio_to_fixed"],
        "mean_sbs_mae": summary["mean_sbs_mae"]
        <= THRESHOLDS["maximum_mean_sbs_mae"],
        "p95_frame_sbs_mae": summary["p95_frame_sbs_mae"]
        <= THRESHOLDS["maximum_p95_frame_sbs_mae"],
        "mean_edge_sbs_mae": summary["mean_edge_sbs_mae"]
        <= THRESHOLDS["maximum_mean_edge_sbs_mae"],
        "large_channel_error_fraction": summary["mean_channels_over_8_fraction"]
        <= THRESHOLDS["maximum_mean_channels_over_8_fraction"],
        "temporal_change_error": summary["p95_temporal_change_error"]
        <= THRESHOLDS["maximum_p95_temporal_change_error"],
    }
    summary["checks"] = checks
    summary["automated_gate_passed"] = all(checks.values())
    return summary


def evaluate_clip(name, DeviceEngine, policy, output_root):
    source = PublicFrames(name, 60)
    frames = [np.ascontiguousarray(frame) for frame in source]
    flags = scene_flags(frames, policy.scene_cut_threshold)
    height, width = frames[0].shape[:2]
    engine = create_engine(DeviceEngine)
    rows = []
    worst = []
    last_fresh = None
    last_fresh_depth = None
    previous_reference = None
    previous_candidate = None
    video_path = output_root / "review" / f"{name}.mp4"
    try:
        engine.reset("start")
        with NvofDeviceWarp(width, height) as warp:
            with (
                SourcePost(
                    engine, width, height, policy, dll_path=POST_DLL
                ) as reference_post,
                SourcePost(
                    engine,
                    width,
                    height,
                    policy,
                    dll_path=POST_DLL,
                    stream=warp.stream,
                ) as candidate_post,
                ReviewWriter(video_path) as writer,
            ):
                for index, (frame, cut) in enumerate(zip(frames, flags)):
                    if cut and index:
                        engine.reset("scene_cut")
                    kind, source_index = cadence_decision(index, cut, last_fresh)
                    depth_token = engine.infer_device(frame)
                    warp_token = None
                    try:
                        # The wrapper may leave its final resize queued on the
                        # producer stream. Only the diagnostic host readback
                        # needs an explicit wait; device consumers use events.
                        engine.stream.synchronize()
                        reference_depth = np.ascontiguousarray(
                            depth_token.tensor.detach().cpu().numpy()[0]
                        )
                        if kind == "warped":
                            candidate_token, _, candidate_depth, valid, timing = (
                                warp.warp(frame, diagnostic=True)
                            )
                            warp_token = candidate_token
                        else:
                            candidate_token, candidate_depth, timing = warp.seed_pointer(
                                frame, depth_token, diagnostic=True
                            )
                            valid = np.ones((height, width), np.uint8)
                            last_fresh = index
                        # Seed must copy the pristine model output before the
                        # reference post context normalizes its source buffer.
                        reference_eyes = reference_post.render_pointer(
                            frame,
                            depth_token.pointer,
                            producer_stream=depth_token.stream,
                            reset=cut,
                        )
                        candidate_eyes = candidate_post.render_pointer(
                            frame,
                            candidate_token.pointer,
                            producer_stream=candidate_token.stream,
                            reset=cut,
                        )
                    finally:
                        if warp_token is not None:
                            warp.complete(warp_token, retain=False)
                        engine.complete_device(depth_token)

                    reference_sbs = combined(reference_eyes)
                    candidate_sbs = combined(candidate_eyes)
                    current_normalized = normalize(reference_depth)
                    candidate_normalized = normalize(candidate_depth)
                    mask = valid != 0
                    depth_mae = float(
                        np.abs(current_normalized - candidate_normalized)[mask].mean()
                    )
                    fixed_mae = None
                    if kind == "warped":
                        fixed_mae = float(
                            np.abs(current_normalized - last_fresh_depth)[mask].mean()
                        )
                    reference_change = temporal_change(reference_sbs, previous_reference)
                    candidate_change = temporal_change(candidate_sbs, previous_candidate)
                    metrics = output_metrics(reference_sbs, candidate_sbs)
                    row = {
                        "frame": index,
                        "cut": bool(cut),
                        "reference_depth_frame": index,
                        "candidate_kind": kind,
                        "candidate_source_depth_frame": source_index,
                        "fresh_depth_exact": bool(
                            np.array_equal(reference_depth, candidate_depth)
                        )
                        if kind != "warped"
                        else None,
                        "valid_fraction": float(mask.mean()),
                        "depth_mae": depth_mae,
                        "fixed_prior_depth_mae": fixed_mae,
                        "reference_temporal_change": reference_change,
                        "candidate_temporal_change": candidate_change,
                        "temporal_change_error": abs(reference_change - candidate_change)
                        if reference_change is not None
                        else None,
                        "warp_timing_us": timing,
                        **metrics,
                    }
                    rows.append(row)
                    if kind != "warped":
                        last_fresh_depth = current_normalized
                    review = review_frame(
                        reference_eyes, candidate_eyes, index, kind, source_index
                    )
                    writer.write(review)
                    item = (row["sbs_mae"], index, review.copy())
                    if len(worst) < 3:
                        heapq.heappush(worst, item)
                    elif item[:2] > worst[0][:2]:
                        heapq.heapreplace(worst, item)
                    previous_reference = reference_sbs
                    previous_candidate = candidate_sbs
        telemetry = engine.telemetry()
    finally:
        engine.close()

    stills = []
    still_root = output_root / "stills"
    still_root.mkdir(parents=True, exist_ok=True)
    for error, index, image in sorted(worst, reverse=True):
        path = still_root / f"{name}-frame-{index:02d}.png"
        if not cv2.imwrite(str(path), cv2.cvtColor(image, cv2.COLOR_RGB2BGR)):
            raise RuntimeError("Review still write failed")
        stills.append(
            {
                "frame": index,
                "sbs_mae": error,
                "path": str(path.resolve()),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    media = verify_video(video_path)
    summary = summarize(rows)
    summary["media_passed"] = media["passed"] and len(stills) == 3
    summary["ownership_cleanup_passed"] = not telemetry["pending_device_depth"]
    summary["automated_gate_passed"] = (
        summary["automated_gate_passed"]
        and summary["media_passed"]
        and summary["ownership_cleanup_passed"]
    )
    return {
        "input": str(source.path.resolve()),
        "input_sha256": hashlib.sha256(source.path.read_bytes()).hexdigest(),
        "scene_reset_indices": [index for index, cut in enumerate(flags) if cut],
        "rows": rows,
        "summary": summary,
        "review_video": {"path": str(video_path.resolve()), **media},
        "worst_stills": stills,
        "engine": telemetry,
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
        "automated_gate_passed": False,
        "candidate_accepted": False,
        "visual_review": "required",
        "scheduler_authorized": False,
        "scope": (
            "Full 60-frame quality comparison with oVDA inferred on every frame. "
            "No inference saving, asynchronous overlap, live FPS, sustained, "
            "native-presentation, perceptual-equivalence, or VR-comfort claim."
        ),
        "attribution": ATTRIBUTION,
        "thresholds": THRESHOLDS,
        "warp_manifest": checked_manifest(),
        "clips": {},
    }
    post_manifest = json.loads(
        (POST_DLL.parent / "build-manifest.json").read_text(encoding="utf-8-sig")
    )
    post_hash = hashlib.sha256(POST_DLL.read_bytes()).hexdigest()
    if post_hash.lower() != post_manifest.get("dll_sha256", "").lower():
        raise ValueError("CUDA post/SBS DLL checksum mismatch")
    report["post_sbs_dll_sha256"] = post_hash

    def save():
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    save()
    _, DeviceEngine, _ = engine_classes()
    from screento3d_app.live_policy import resolve_live

    policy = resolve_live("video-quality")
    with ExitStack() as stack:
        stack.enter_context(os.add_dll_directory(str(RUNTIME)))
        for name in CLIPS:
            report["clips"][name] = evaluate_clip(
                name, DeviceEngine, policy, args.output
            )
            save()
            print(
                json.dumps({name: report["clips"][name]["summary"]}, indent=2),
                flush=True,
            )
    report["passed"] = True
    report["automated_gate_passed"] = all(
        clip["summary"]["automated_gate_passed"]
        for clip in report["clips"].values()
    )
    save()
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "automated_gate_passed": report["automated_gate_passed"],
                "candidate_accepted": report["candidate_accepted"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
