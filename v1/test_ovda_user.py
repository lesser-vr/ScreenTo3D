"""Real local oVDA user-path gate using pinned public footage by default."""

import argparse
import json
import shutil
import subprocess
import uuid
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from depthsbs_app import ovda, pipeline
from depthsbs_app.main import build_parser, run_worker
from depthsbs_app.resources import configure_media_tools
from evaluate_depth_models import inspect_media, sha

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "out/gpu-preview/DepthSBS-GPU-Preview/_internal/ffmpeg"
RUNTIME = Path("C:/TensorRT/TensorRT-11.2.1.2/bin")
ENGINES = ROOT / "out/ovda-local"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--original", type=Path, default=ROOT / "out/public-live-default/OfficeWalk.mp4"
    )
    parser.add_argument(
        "--cuts", type=Path, default=ROOT / "out/public-live-default/ParkingGarage.mp4"
    )
    args = parser.parse_args()
    root = ROOT / "out/ovda-user-validation" / uuid.uuid4().hex
    root.mkdir(parents=True)
    attributions = (
        args.cuts.parent / "ATTRIBUTION.txt",
        args.cuts.parent.parent / "ATTRIBUTION.txt",
    )
    attribution = next((path for path in attributions if path.is_file()), None)
    if attribution is not None:
        shutil.copyfile(attribution, root / "ATTRIBUTION.txt")
    print(root, flush=True)
    report = {
        "passed": False,
        "clips": [],
        "failures": [],
        "source_hashes": {str(p): sha(p) for p in (args.original, args.cuts)},
    }
    configure_media_tools(MEDIA)

    def ffmpeg(arguments):
        subprocess.run(
            [
                str(MEDIA / "ffmpeg.exe"),
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                *arguments,
            ],
            check=True,
        )

    long_clip = root / "cuts-600.mp4"
    ffmpeg(
        [
            "-stream_loop",
            "4",
            "-i",
            str(args.cuts),
            "-frames:v",
            "600",
            "-an",
            "-c:v",
            "libx264",
            "-crf",
            "18",
            str(long_clip),
        ]
    )
    audio_clip = root / "1080-hevc-audio.mp4"
    ffmpeg(
        [
            "-i",
            str(args.cuts),
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000",
            "-t",
            "1",
            "-vf",
            "scale=1920:1080",
            "-c:v",
            "libx265",
            "-preset",
            "fast",
            "-x265-params",
            "log-level=error",
            "-c:a",
            "aac",
            "-shortest",
            str(audio_clip),
        ]
    )
    cls = ovda.runtime_class()
    real_infer = cls.infer
    samples = []

    def observed(engine, frame):
        result = real_infer(engine, frame)
        if engine.calls % 30 == 0:
            samples.append(engine.telemetry())
        return result

    try:
        for name, source, mode, codec in (
            ("original", args.original, "video-quality", "h264"),
            ("long-cuts", long_clip, "video-quality", "h264"),
            ("1080-hevc-audio", audio_clip, "video-quality", "hevc"),
        ):
            samples.clear()
            status = root / f"{name}.jsonl"
            output = root / f"{name}-sbs.mp4"
            options = build_parser().parse_args(
                [
                    "--worker",
                    "--depth-backend",
                    "ovda-small-c16",
                    "--ovda-engine-dir",
                    str(ENGINES),
                    "--runtime-dir",
                    str(RUNTIME),
                    "--ovda-noncommercial",
                    "--mode",
                    mode,
                    "--output-codec",
                    codec,
                    "--input",
                    str(source),
                    "--output",
                    str(output),
                    "--status-file",
                    str(status),
                ]
            )
            with patch.object(cls, "infer", observed):
                assert run_worker(options) == 0, status
            events = [
                json.loads(line)
                for line in status.read_text(encoding="utf-8").splitlines()
            ]
            complete = [e for e in events if e["event"] == "complete"]
            assert len(complete) == 1
            metadata = pipeline.probe_video(source)
            inspect_media(output, metadata)
            streams = json.loads(
                subprocess.check_output(
                    [
                        str(MEDIA / "ffprobe.exe"),
                        "-v",
                        "error",
                        "-show_streams",
                        "-of",
                        "json",
                        str(output),
                    ]
                )
            )["streams"]
            actual = next(s for s in streams if s["codec_type"] == "video")
            assert actual["codec_name"] == ("hevc" if codec == "hevc" else "h264")
            numerator, denominator = map(int, actual["avg_frame_rate"].split("/"))
            assert abs(numerator / denominator - metadata["fps"]) < 0.001
            assert samples and all(
                s["cache_slots"] == 16 and s["cache_used"] == 15 for s in samples
            )
            assert len({s["cache_bytes"] for s in samples}) == 1
            if name == "long-cuts":
                assert metadata["total_frames"] == 600
                assert (
                    samples[-1]["completed_inferences"] == 600
                    and samples[-1]["resets"] >= 10
                )
            report["clips"].append(
                {
                    "name": name,
                    "input_sha256": sha(source),
                    "metadata": metadata,
                    "result": complete[0],
                    "samples": list(samples),
                }
            )
            print("PASS " + name, flush=True)
        # The public binding remains bounded and preserves existing output on abort.
        for name, source in (("896", args.original), ("924", args.cuts)):
            for failure in (False, True):
                backend = ovda.binding(ENGINES, RUNTIME, True)
                factory = backend.engine_factory
                owned = []

                def wrapped(
                    progress, factory=factory, owned=owned, failure=failure
                ):
                    engine = factory(progress)
                    owned.append(engine)
                    if failure:
                        original_infer = engine.infer

                        def fail(frame):
                            if engine.calls == 3:
                                raise RuntimeError("injected oVDA failure")
                            return original_infer(frame)

                        engine.infer = fail
                    return engine

                backend = replace(backend, engine_factory=wrapped)
                output = root / f"{name}-{failure}-preserved.mp4"
                sentinel = b"existing user output"
                output.write_bytes(sentinel)
                cancel = root / f"{name}.cancel"

                def progress(event, failure=failure, cancel=cancel):
                    if (
                        not failure
                        and event.get("event") == "progress"
                        and event["frame"] >= 1
                    ):
                        cancel.touch()

                try:
                    pipeline.convert_video(
                        source,
                        output,
                        "video-quality",
                        progress,
                        None if failure else cancel,
                        depth_backend=backend,
                    )
                except (InterruptedError, RuntimeError) as error:
                    assert (failure and "injected oVDA failure" in str(error)) or (
                        not failure and isinstance(error, InterruptedError)
                    )
                else:
                    raise AssertionError("Abort expected")
                assert output.read_bytes() == sentinel
                assert (
                    len(owned) == 1
                    and owned[0].closed
                    and not owned[0].cache
                    and owned[0].context is None
                )
                report["failures"].append(
                    {"profile": name, "failure": failure, "passed": True}
                )
        assert report["source_hashes"] == {
            str(p): sha(p) for p in (args.original, args.cuts)
        }
        report["passed"] = True
    finally:
        (root / "report.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        print(root / "report.json", flush=True)


if __name__ == "__main__":
    main()
