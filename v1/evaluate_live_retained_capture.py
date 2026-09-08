"""Predeclared actual-app gate for retained mapped capture frames."""

import argparse
import hashlib
import json
import statistics
from pathlib import Path

import numpy as np


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def percent_change(current, candidate):
    return (candidate / current - 1) * 100


def event_duration_p50(rows):
    values = [
        (event[2] - event[1]) / 1e6
        for row in rows
        for event in row["capture_events"]
        if event[4] == 0
    ]
    if not values:
        raise ValueError("No published capture callback events")
    return float(np.percentile(values, 50))


def summarize(path):
    environment = json.loads((path / "environment.json").read_text(encoding="utf-8"))
    rows = json.loads((path / "runs.json").read_text(encoding="utf-8"))
    if len(rows) != 5:
        raise ValueError("Retained capture gate requires five windows per path")
    rates = {
        "capture_published_fps": statistics.median(
            row["capture_observation_rates"]["published_fps"] for row in rows
        ),
        "processed_fps": statistics.median(row["processed_fps"] for row in rows),
        "output_fps": statistics.median(row["output_swap_fps"] for row in rows),
    }
    worker_cpu = statistics.median(
        row["worker_cpu_seconds"] / row["seconds"] for row in rows
    )
    memory = [sample[1] for row in rows for sample in row["memory"]]
    return {
        "environment": environment,
        "runs_sha256": sha256(path / "runs.json"),
        "callback_duration_p50_ms": event_duration_p50(rows),
        "worker_cpu_cores": worker_cpu,
        "worker_private_p95_bytes": float(np.percentile(memory, 95)),
        **rates,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--minimum-callback-improvement-percent", type=float, default=80
    )
    parser.add_argument(
        "--minimum-worker-cpu-improvement-percent", type=float, default=5
    )
    parser.add_argument("--maximum-rate-regression-percent", type=float, default=1)
    parser.add_argument("--maximum-memory-increase-mib", type=float, default=64)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)

    current = summarize(args.current)
    candidate = summarize(args.candidate)
    left, right = current["environment"], candidate["environment"]
    comparable = {
        key: left.get(key) == right.get(key)
        for key in (
            "commit",
            "model_sha256",
            "fixture",
            "source_process",
            "presentation_target_hz",
            "live_path",
            "live_dll_sha256",
            "native_dll_sha256",
            "texture_runtime_sha256",
            "qml_sha256",
            "warmup_seconds",
        )
    }
    comparable["current_has_no_candidate"] = left.get("capture_candidate") is None
    comparable["candidate_is_retained"] = (
        right.get("capture_candidate", {}).get("name")
        == "retained-mapped-capture-frame"
    )
    callback_improvement = (
        1 - candidate["callback_duration_p50_ms"] / current["callback_duration_p50_ms"]
    ) * 100
    cpu_improvement = (
        1 - candidate["worker_cpu_cores"] / current["worker_cpu_cores"]
    ) * 100
    rate_changes = {
        key: percent_change(current[key], candidate[key])
        for key in ("capture_published_fps", "processed_fps", "output_fps")
    }
    memory_increase_mib = (
        candidate["worker_private_p95_bytes"] - current["worker_private_p95_bytes"]
    ) / 2**20
    acceptance = {
        "minimum_callback_improvement_percent": args.minimum_callback_improvement_percent,
        "minimum_worker_cpu_improvement_percent": args.minimum_worker_cpu_improvement_percent,
        "maximum_rate_regression_percent": args.maximum_rate_regression_percent,
        "maximum_memory_increase_mib": args.maximum_memory_increase_mib,
    }
    gates = {
        "comparable_environment": all(comparable.values()),
        "callback_improvement": callback_improvement
        >= args.minimum_callback_improvement_percent,
        "worker_cpu_improvement": cpu_improvement
        >= args.minimum_worker_cpu_improvement_percent,
        "rates": all(
            value >= -args.maximum_rate_regression_percent
            for value in rate_changes.values()
        ),
        "memory": memory_increase_mib <= args.maximum_memory_increase_mib,
    }
    report = {
        "passed": all(gates.values()),
        "scope": (
            "Sequential actual-app 3840x2160 input/per-eye, 7680x2160 Full SBS, "
            "Balanced, 60 Hz, five measured windows after warmup. Callback timing "
            "starts after native readback/GIL entry; output IDs are not scanout."
        ),
        "acceptance": acceptance,
        "comparable": comparable,
        "gates": gates,
        "current": current,
        "candidate": candidate,
        "callback_improvement_percent": callback_improvement,
        "worker_cpu_improvement_percent": cpu_improvement,
        "rate_changes_percent": rate_changes,
        "memory_increase_mib": memory_increase_mib,
        "evaluator_sha256": sha256(Path(__file__)),
    }
    args.output.mkdir(parents=True)
    (args.output / "report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps({"passed": report["passed"], "gates": gates}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
