"""Summarize the matched 1080p native/host matrix without promoting support."""

import argparse
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path

import numpy as np


def distribution(values):
    if not values:
        return None
    return dict(
        count=len(values),
        minimum=float(min(values)),
        maximum=float(max(values)),
        **{f"p{q}": float(np.percentile(values, q)) for q in (50, 95, 99)},
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sixty-suffix", default="")
    args = parser.parse_args()
    summaries = []
    benchmark_hashes = set()
    shared_configuration = set()
    provenance = []
    for label, path, hz in (
        ("host30", "gpu", 30),
        ("native30", "gpu-texture", 30),
        ("native60", "gpu-texture", 60),
        ("host60", "gpu", 60),
    ):
        folder = args.root / f"1080p-{label}{args.sixty_suffix if hz == 60 else ''}"
        env = json.loads((folder / "environment.json").read_text())
        runs = json.loads((folder / "runs.json").read_text())
        assert len(runs) == 15 and env["live_path"] == path
        assert env["presentation_target_hz"] == hz
        assert not env["diagnostic_hide_main"] and not env["diagnostic_poll_ms"]
        assert env["fixture"] == "FloorballGame" and env["warmup_seconds"] == 10
        benchmark_hashes.add(env["benchmark_sha256"])
        shared_configuration.add(
            json.dumps(
                {
                    key: env[key]
                    for key in (
                        "model_sha256",
                        "source_sha256",
                        "qml_sha256",
                        "dpi",
                        "resolve_impl",
                        "host_bridge",
                        "live_capture_interval_ms",
                    )
                },
                sort_keys=True,
            )
        )
        assert not env["diagnostic_profile"] and not env["legacy_poll"]
        gpu = []
        with (folder / "gpu-samples.csv").open(encoding="utf-8") as stream:
            for row in csv.reader(stream):
                assert len(row) == 8, row
                # NVIDIA timestamps are local wall time; benchmark bounds are UTC epoch.
                when = datetime.strptime(
                    row[0].strip(), "%Y/%m/%d %H:%M:%S.%f"
                ).timestamp()
                assert int(row[1]) == 0, "Matrix requires the single recorded device"
                gpu.append((when * 1e9, *map(float, row[2:])))
        provenance.append(
            dict(
                batch=label,
                environment=env,
                files={
                    name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
                    for name in (
                        "runs.json",
                        "runs.csv",
                        "environment.json",
                        "gpu-samples.csv",
                    )
                },
            )
        )
        for mode in ("performance", "balanced", "video-quality"):
            selected = [row for row in runs if row["mode"] == mode]
            assert len(selected) == 5 and {r["repeat"] for r in selected} == set(
                range(5)
            )
            assert all(
                r["size"] == "1920x1080" and r["seconds"] >= 10 for r in selected
            )
            assert all(
                (r["report"]["width"], r["report"]["height"]) == (3840, 1080)
                for r in selected
            )
            assert selected[-1]["overload"]["replaced"] > 0
            samples = [
                g
                for g in gpu
                if any(r["wall_start_ns"] <= g[0] <= r["wall_end_ns"] for r in selected)
            ]
            assert len(samples) >= 40, "Insufficient device samples in measured windows"
            ages = [
                age
                for r in selected
                for age in r.get("paint_to_output_readback_ms", [])
            ]
            summaries.append(
                dict(
                    path=path,
                    hz=hz,
                    mode=mode,
                    output_fps=distribution([r["output_swap_fps"] for r in selected]),
                    processed_fps=distribution([r["processed_fps"] for r in selected]),
                    rate_kind=selected[0]["output_rate_kind"],
                    gui_source_cpu_cores=distribution(
                        [r["gui_cpu_seconds"] / r["seconds"] for r in selected]
                    ),
                    worker_cpu_cores=distribution(
                        [r["worker_cpu_seconds"] / r["seconds"] for r in selected]
                    ),
                    provider_requests_fps=distribution(
                        [r["image_provider_request_fps"] for r in selected]
                    ),
                    gpu_utilization_percent=distribution([g[1] for g in samples]),
                    gpu_memory_mib=distribution([g[3] for g in samples]),
                    gpu_power_watts=distribution([g[4] for g in samples]),
                    gpu_temperature_c=distribution([g[5] for g in samples]),
                    gui_private_bytes=distribution(
                        [v for r in selected for v in r["gui_private_bytes"]]
                    ),
                    worker_private_bytes=distribution(
                        [v[1] for r in selected for v in r["memory"]]
                    ),
                    readback_age_ms=distribution(ages),
                    readback_attempts=sum(r.get("clock_attempts", 0) for r in selected),
                    overload=selected[-1]["overload"],
                )
            )
    assert len(benchmark_hashes) == 1, "Mixed benchmark revisions"
    assert len(shared_configuration) == 1, (
        "Model, source, policy or UI changed between batches"
    )
    qualifications = []
    for hz in (30, 60):
        batch_envs = [
            p["environment"]
            for p in provenance
            if p["environment"]["presentation_target_hz"] == hz
        ]
        preflights = [next(csv.reader([e["gpu_preflight"]])) for e in batch_envs]
        idle_utilization = [float(p[1].split()[0]) for p in preflights]
        baseline_memory = [float(p[2].split()[0]) for p in preflights]
        qualifications.append(
            dict(
                hz=hz,
                preflight_gpu_percent=idle_utilization,
                preflight_memory_mib=baseline_memory,
                background_warning=any(idle_utilization)
                or max(baseline_memory) - min(baseline_memory) > 512,
                note="Nonzero preflight activity or >512 MiB baseline change flags a confound; passing this screen does not prove isolation",
            )
        )
    report = dict(
        completed=True,
        qualifications=qualifications,
        summaries=summaries,
        provenance=provenance,
        local_timezone=str(datetime.now().astimezone().tzinfo),
        scope="Five 10-second repetitions after 10-second warmup per condition; device-wide GPU; GUI CPU includes source; readback age is not physical-display latency; not a soak or sustained support gate",
    )
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "summary.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
