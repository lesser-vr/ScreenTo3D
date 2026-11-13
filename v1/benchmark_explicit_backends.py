"""Matched, isolated file-pipeline benchmark with explicit backend identities."""

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time

from evaluate_depth_models import inspect_media

ROOT = Path(__file__).resolve().parents[1]
MODELS = ("small", "vda", "ovda")
EXPECTED = {
    "small": ("da2-small", "tensorrt"),
    "vda": ("vda-small", "tensorrt-fp32"),
    "ovda": ("ovda-small-c16", "tensorrt-fp32"),
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.repeats <= 0 or args.output.exists():
        raise ValueError("Positive repeats and fresh output required")
    args.output.mkdir(parents=True)
    from screento3d_app.pipeline import probe_video
    from screento3d_app.resources import configure_media_tools

    media = ROOT / "out/gpu-preview/ScreenTo3D-GPU-Preview/_internal/ffmpeg"
    configure_media_tools(media)
    metadata = probe_video(args.input, output_codec="h264")
    assert (metadata["width"], metadata["height"], metadata["total_frames"]) == (
        1920,
        1080,
        60,
    )
    rows = []
    report = dict(
        passed=False,
        input=str(args.input.resolve()),
        input_sha256=digest(args.input),
        metadata=metadata,
        rows=rows,
        renderer="cuda",
        mode="video-quality",
        note="File pipeline potential; no live capture/output or streaming-latency claim",
    )
    try:
        for round_index in range(args.repeats + 1):
            for model in MODELS:
                stem = f"r{round_index}-{model}"
                output = args.output / f"{stem}.mp4"
                log_path = args.output / f"{stem}.log"
                command = [
                    sys.executable,
                    str(ROOT / "v1/evaluate_ovda_expansion.py"),
                    "--worker",
                    "--input",
                    str(args.input.resolve()),
                    "--output",
                    str(output.resolve()),
                    "--model",
                    model,
                    "--renderer",
                    "cuda",
                ]
                started = time.perf_counter()
                with log_path.open("w", encoding="utf-8") as log:
                    completed = subprocess.run(
                        command, stdout=log, stderr=subprocess.STDOUT
                    )
                wall = time.perf_counter() - started
                if completed.returncode:
                    raise RuntimeError(f"{model} worker failed; inspect {log_path}")
                result_path = output.with_suffix(".json")
                result = json.loads(result_path.read_text(encoding="utf-8"))
                identity = (
                    result["depth_backend"]["model_id"],
                    result["depth_backend"]["runtime"],
                )
                assert identity == EXPECTED[model], (model, identity)
                inspect_media(output, metadata)
                row = dict(
                    round=round_index,
                    warmup=round_index == 0,
                    backend=model,
                    resolved_backend=identity[0],
                    resolved_runtime=identity[1],
                    processing_fps=result["processing_fps"],
                    worker_job_seconds=result["worker_job_seconds"],
                    process_wall_seconds=wall,
                    stages=result["telemetry"]["stages"],
                    model_telemetry=result["telemetry"]["resources"],
                    output_sha256=digest(output),
                    result_sha256=digest(result_path),
                )
                rows.append(row)
                (args.output / "report.json").write_text(
                    json.dumps(report, indent=2), encoding="utf-8"
                )
                print(
                    json.dumps(
                        {
                            k: row[k]
                            for k in (
                                "round",
                                "warmup",
                                "resolved_backend",
                                "resolved_runtime",
                                "processing_fps",
                            )
                        }
                    ),
                    flush=True,
                )
                # Only the established DA2 control detects a system recurrence.
                if model == "small" and result["processing_fps"] < 10:
                    (args.output / "stop-alert.json").write_text(
                        json.dumps(row, indent=2), encoding="utf-8"
                    )
                    raise RuntimeError(
                        "DA2 Small control collapsed; stop and request monitor-on retest"
                    )
        summary = {}
        for model in MODELS:
            measured = [r for r in rows if r["backend"] == model and not r["warmup"]]
            values = [r["processing_fps"] for r in measured]
            summary[model] = dict(
                resolved_backend=measured[0]["resolved_backend"],
                resolved_runtime=measured[0]["resolved_runtime"],
                median_fps=statistics.median(values),
                minimum_fps=min(values),
                maximum_fps=max(values),
                runs=len(values),
            )
        report["summary"] = summary
        report["passed"] = True
    finally:
        (args.output / "report.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
