"""Public-corpus proxy comparison for raw and centered Offline VDA depth."""

import argparse
import hashlib
import json
import time
from itertools import chain
from pathlib import Path

from screento3d_app.config import MODES
from screento3d_app.depth_backend import vda_offline_binding
from screento3d_app.offline_depth import is_scene_cut
from public_test_media import ATTRIBUTION, CORPUS, SOURCES, PublicFrames
from temporal_diagnostics import TemporalProbe

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME = Path("C:/TensorRT/TensorRT-11.2.1.2/bin")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def add_with_cut(probe, previous, frame, depth, threshold):
    cut = previous is not None and is_scene_cut(previous, frame, threshold)
    probe.add(frame, depth, cut=cut)
    return frame.copy(), cut


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clip", choices=tuple(SOURCES), default="FloorballGame")
    parser.add_argument("--cut-clip", choices=tuple(SOURCES))
    parser.add_argument("--frames", type=int, default=120)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--engine-dir", type=Path, default=ROOT / "out/vda-local")
    parser.add_argument("--runtime-dir", type=Path, default=DEFAULT_RUNTIME)
    args = parser.parse_args()
    if not 2 <= args.frames <= 124:
        raise ValueError("Diagnostic frame count must be from 2 through 124")
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite diagnostic report: {output}")

    if args.cut_clip == args.clip:
        raise ValueError("Cut diagnostic requires two distinct public clips")
    annotated_cut_frame = None
    if args.cut_clip is None:
        source = PublicFrames(args.clip, args.frames)
        names = [args.clip]
    else:
        annotated_cut_frame = args.frames // 2
        source = chain(
            PublicFrames(args.clip, annotated_cut_frame),
            PublicFrames(args.cut_clip, args.frames - annotated_cut_frame),
        )
        names = [args.clip, args.cut_clip]
    binding = vda_offline_binding(args.engine_dir, args.runtime_dir)
    binding.input_validator({"width": 1920, "height": 1080})
    window = binding.offline_processor_factory()
    raw_probe, fused_probe = TemporalProbe(), TemporalProbe()
    raw_previous = fused_previous = inference_previous = None
    raw_cut_frames = []
    fused_cut_frames = []
    policy = MODES["offline-quality"]
    started = time.perf_counter()
    with binding.engine_factory(None) as engine:
        binding.reset(engine, "start")
        for index, frame in enumerate(source):
            cut = inference_previous is not None and is_scene_cut(
                inference_previous, frame, policy.scene_cut_threshold
            )
            if cut:
                binding.reset(engine, "scene_cut")
                raw_cut_frames.append(index)
            depth = binding.infer(engine, binding.prepare(frame))
            raw_previous, raw_probe_cut = add_with_cut(
                raw_probe, raw_previous, frame, depth, policy.scene_cut_threshold
            )
            if raw_probe_cut != cut:
                raise RuntimeError(
                    "Raw diagnostic and inference cut predicates diverged"
                )
            for output_frame, output_depth in window.submit(
                frame, depth, cut_before=cut
            ):
                fused_previous, fused_cut = add_with_cut(
                    fused_probe,
                    fused_previous,
                    output_frame,
                    output_depth,
                    policy.scene_cut_threshold,
                )
                if fused_cut:
                    fused_cut_frames.append(len(fused_probe.rows) - 1)
            inference_previous = frame.copy()
        for output_frame, output_depth in window.finish():
            fused_previous, fused_cut = add_with_cut(
                fused_probe,
                fused_previous,
                output_frame,
                output_depth,
                policy.scene_cut_threshold,
            )
            if fused_cut:
                fused_cut_frames.append(len(fused_probe.rows) - 1)
        engine_telemetry = engine.telemetry()

    raw = raw_probe.report()
    fused = fused_probe.report()
    if len(raw["rows"]) != args.frames or len(fused["rows"]) != args.frames:
        raise RuntimeError("Diagnostic changed frame count")
    if annotated_cut_frame is not None and (
        annotated_cut_frame not in raw_cut_frames
        or annotated_cut_frame not in fused_cut_frames
    ):
        raise RuntimeError("Annotated public hard cut was not isolated")
    metrics = ("aligned_mae", "edge_aligned_mae", "unaligned_mae")
    ratios = {
        key: (
            fused["summary"][key] / raw["summary"][key]
            if raw["summary"][key] not in (None, 0.0)
            and fused["summary"][key] is not None
            else None
        )
        for key in metrics
    }
    source_paths = [CORPUS / f"{name}.mp4" for name in names]
    report = {
        "passed": True,
        "scope": (
            "Public 1080p source, VDA Small, first <=124 frames. Farneback-aligned "
            "normalized-depth change proxy only; no ground truth, stereo comfort, "
            "ghosting, full-video, or quality-winner claim. Lower ratio is steadier."
        ),
        "clips": names,
        "frames": args.frames,
        "annotated_cut_frame": annotated_cut_frame,
        "sources": [str(path.resolve()) for path in source_paths],
        "source_sha256": {path.stem: sha256(path) for path in source_paths},
        "attribution": ATTRIBUTION,
        "backend": binding.describe(),
        "raw": raw,
        "offline": fused,
        "offline_to_raw_ratios": ratios,
        "raw_cut_frames": raw_cut_frames,
        "fused_cut_frames": fused_cut_frames,
        "window": window.telemetry(),
        "engine": engine_telemetry,
        "elapsed_seconds": time.perf_counter() - started,
        "source_hashes": {
            name: sha256(ROOT / name)
            for name in (
                "v1/evaluate_offline_depth.py",
                "v1/screento3d_app/offline_depth.py",
                "v1/temporal_diagnostics.py",
                "v1/public_test_media.py",
            )
        },
    }
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(output), "ratios": ratios}, indent=2))


if __name__ == "__main__":
    main()
