"""Verify and summarize the three-mode native60 guarded baseline artifacts."""

import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh summary path")
    modes = {}
    common = None
    for mode in ("performance", "balanced", "video-quality"):
        folder = args.root / f"{mode}-native60"
        assert not (folder / "stop-alert.json").exists(), (
            "Stopped run is not a baseline"
        )
        env = json.loads((folder / "environment.json").read_text())
        rows = json.loads((folder / "runs.json").read_text())
        assert len(rows) == 5 and env["warmup_seconds"] == 10
        assert env["source_process"] and env["live_path"] == "gpu-texture"
        assert env["presentation_target_hz"] == 60
        assert env["fixture"] == "FloorballGame"
        assert env["abort_output_below_fps"] == 20 and env["capture_telemetry"]
        assert not env["diagnostic_hide_main"] and not env["diagnostic_poll_ms"]
        assert not env["qsg_no_vsync"] and not env["qsg_render_loop"]
        shared = {
            key: env[key]
            for key in (
                "benchmark_sha256",
                "source_harness_sha256",
                "model_sha256",
                "source_sha256",
                "qml_sha256",
                "native_dll_sha256",
                "texture_runtime_sha256",
                "live_dll_sha256",
                "dpi",
                "resolve_impl",
                "host_bridge",
                "live_capture_interval_ms",
                "os",
                "python",
                "qt",
            )
        }
        # Device/driver/capacity are fixed; power and clocks are run-time samples.
        shared["gpu_identity"] = [value.strip() for value in env["gpu"].split(",")[:3]]
        if common is None:
            common = shared
        else:
            assert shared == common, "Code/model/configuration mismatch"
        for i, row in enumerate(rows):
            assert row["repeat"] == i and row["mode"] == mode
            assert row["size"] == "1920x1080" and row["seconds"] >= 10
            assert (row["report"]["width"], row["report"]["height"]) == (3840, 1080)
            assert row["output_rate_kind"] == "distinct native afterFrameEnd IDs"
        assert rows[-1]["overload"]["slots"] == 2
        assert rows[-1]["overload"]["pending"] <= 1
        assert rows[-1]["overload"]["replaced"] > 0
        rates = {}
        for key in ("source_paint_fps", "processed_fps", "output_swap_fps"):
            values = [r[key] for r in rows]
            rates[key] = dict(
                minimum=min(values), maximum=max(values), mean=sum(values) / len(values)
            )
        modes[mode] = dict(
            rates=rates,
            readback_summary_ms=rows[-1]["clock_summary_ms"],
            readback_valid=len(rows[-1]["paint_to_output_readback_ms"]),
            readback_attempts=rows[-1]["clock_attempts"],
            overload=rows[-1]["overload"],
            artifact_sha256={
                name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
                for name in (
                    "runs.json",
                    "runs.csv",
                    "environment.json",
                    "gpu-samples.csv",
                )
            },
        )
    report = dict(
        passed=True,
        modes=modes,
        common=common,
        scope="Guarded 1080p native60 three-mode baseline; source clock/readback is not photon latency. No sustained/VR/other-hardware acceptance.",
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps(modes, indent=2))


if __name__ == "__main__":
    main()
