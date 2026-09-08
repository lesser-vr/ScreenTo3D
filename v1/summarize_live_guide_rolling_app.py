"""Validate and summarize matched current/rolling actual-app benchmark runs."""

import argparse
import hashlib
import json
import statistics
from pathlib import Path


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def distribution(values):
    return {
        "median": statistics.median(values),
        "minimum": min(values),
        "maximum": max(values),
        "values": values,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--quality-report", type=Path, required=True)
    parser.add_argument("--native-boundary-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--minimum-window-seconds", type=float, default=6)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)

    data = {}
    for name, root in (("current", args.current), ("candidate", args.candidate)):
        data[name] = {
            "runs": json.loads((root / "runs.json").read_text(encoding="utf-8")),
            "environment": json.loads(
                (root / "environment.json").read_text(encoding="utf-8")
            ),
            "analysis": json.loads(
                (root / "gpu-boundary-analysis.json").read_text(encoding="utf-8")
            ),
        }
        if (root / "stop-alert.json").exists():
            raise ValueError(f"{name} run tripped its output-rate guard")

    current, candidate = data["current"], data["candidate"]
    quality_path = args.quality_report.resolve()
    native_path = args.native_boundary_report.resolve()
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    native = json.loads(native_path.read_text(encoding="utf-8"))
    if not quality.get("passed") or not native.get("passed"):
        raise ValueError("Required earlier candidate gate did not pass")

    shared_environment = (
        "benchmark_sha256",
        "model_sha256",
        "dpi",
        "fixture",
        "source_harness_sha256",
        "presentation_target_hz",
        "host_bridge",
        "live_path",
        "native_dll_sha256",
        "texture_runtime_sha256",
        "resolve_impl",
        "qml_sha256",
        "warmup_seconds",
        "abort_output_below_fps",
    )
    mismatches = [
        key
        for key in shared_environment
        if current["environment"][key] != candidate["environment"][key]
    ]
    if mismatches:
        raise ValueError(f"Environment mismatch: {mismatches}")
    for name, item in data.items():
        runs = item["runs"]
        if len(runs) != 5 or {row["size"] for row in runs} != {"3840x2160"}:
            raise ValueError(f"Unexpected {name} run matrix")
        if {row["mode"] for row in runs} != {"balanced"}:
            raise ValueError(f"Unexpected {name} mode")
        if not all(row["seconds"] >= args.minimum_window_seconds for row in runs):
            raise ValueError(f"Short {name} measurement window")
        checks = item["analysis"]["explicit_transfers"]["formula_checks"]
        if not all(checks.values()):
            raise ValueError(f"{name} transfer formula failed")

    candidate_hash = candidate["environment"]["live_dll_sha256"]
    if current["environment"]["guide_candidate"] is not None:
        raise ValueError("Current path unexpectedly selected a guide candidate")
    if candidate["environment"]["guide_candidate"]["dll_sha256"] != candidate_hash:
        raise ValueError("Candidate environment hash mismatch")
    if quality["environment"]["candidate_dll_sha256"] != candidate_hash:
        raise ValueError("Actual-app DLL differs from quality-approved candidate")
    if native["environment"]["candidate_dll_sha256"] != candidate_hash:
        raise ValueError("Actual-app DLL differs from native-boundary candidate")

    rates = {}
    for name, item in data.items():
        rates[name] = {
            key: distribution([row[key] for row in item["runs"]])
            for key in (
                "source_advance_fps",
                "capture_arrival_fps",
                "processed_fps",
                "output_swap_fps",
            )
        }
    current_output = rates["current"]["output_swap_fps"]["median"]
    candidate_output = rates["candidate"]["output_swap_fps"]["median"]
    current_processed = rates["current"]["processed_fps"]["median"]
    candidate_processed = rates["candidate"]["processed_fps"]["median"]
    current_guide = current["analysis"]["gpu_stage_summary"]["guide"]["p50_ms"]
    candidate_guide = candidate["analysis"]["gpu_stage_summary"]["guide"]["p50_ms"]

    report = {
        "validated": True,
        "scope": (
            "Matched sequential actual-app WGC, DA2 Small Balanced, CUDA post, "
            "native texture delivery and Qt output submission at 3840x2160 input "
            "and per eye / 7680x2160 Full SBS. Five windows of at least "
            f"{args.minimum_window_seconds:g} seconds follow a "
            f"{current['environment']['warmup_seconds']:g}-second warmup per path. "
            "This is one scaled public clip and logical "
            "output window, not physical scanout, native-detail quality, VR comfort, "
            "another mode/content/GPU or sustained support."
        ),
        "inputs": {
            "current": str(args.current.resolve()),
            "candidate": str(args.candidate.resolve()),
            "quality_report": str(quality_path),
            "quality_report_sha256": sha256(quality_path),
            "native_boundary_report": str(native_path),
            "native_boundary_report_sha256": sha256(native_path),
        },
        "artifacts": {
            "current_dll_sha256": current["environment"]["live_dll_sha256"],
            "candidate_dll_sha256": candidate_hash,
            "native_delivery_dll_sha256": current["environment"][
                "native_dll_sha256"
            ],
            "texture_runtime_dll_sha256": current["environment"][
                "texture_runtime_sha256"
            ],
        },
        "matched_environment_fields": list(shared_environment),
        "minimum_window_seconds": args.minimum_window_seconds,
        "rates": rates,
        "sampled_guide": {
            "current_p50_ms": current_guide,
            "candidate_p50_ms": candidate_guide,
            "improvement_percent": (1 - candidate_guide / current_guide) * 100,
            "samples_per_path": current["analysis"]["gpu_stage_summary"]["guide"][
                "samples"
            ],
            "scope": "CUDA stream intervals can include host enqueue gaps",
        },
        "effect": {
            "processed_median_improvement_percent": (
                candidate_processed / current_processed - 1
            )
            * 100,
            "output_median_improvement_percent": (
                candidate_output / current_output - 1
            )
            * 100,
            "candidate_output_median_reaches_60_fps": candidate_output >= 60,
            "candidate_output_maximum_reaches_60_fps": rates["candidate"][
                "output_swap_fps"
            ]["maximum"]
            >= 60,
        },
        "clock_readback": {
            name: {
                "valid": len(item["runs"][-1]["paint_to_output_readback_ms"]),
                "attempts": item["runs"][-1]["clock_attempts"],
                "summary_ms": item["runs"][-1]["clock_summary_ms"],
                "scope": "source-paint to Qt output readback; not motion-to-photon",
            }
            for name, item in data.items()
        },
        "transfer_checks": {
            name: item["analysis"]["explicit_transfers"]["formula_checks"]
            for name, item in data.items()
        },
        "decision": (
            "Observed actual-app benefit supports broader candidate validation. "
            "Do not claim 4K60 or change the product default from this single "
            "content/mode sequential comparison."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
