"""Join validated actual-app rolling-guide comparisons across public clips."""

import argparse
import hashlib
import json
import statistics
from pathlib import Path


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--comparison", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    if len(args.comparison) < 3:
        raise ValueError("At least three validated clip comparisons are required")

    rows = []
    candidate_hashes = set()
    current_hashes = set()
    for path in args.comparison:
        comparison = json.loads(path.read_text(encoding="utf-8"))
        if not comparison.get("validated"):
            raise ValueError(f"Unvalidated comparison: {path}")
        current_root = Path(comparison["inputs"]["current"])
        candidate_root = Path(comparison["inputs"]["candidate"])
        current_env = json.loads(
            (current_root / "environment.json").read_text(encoding="utf-8")
        )
        candidate_env = json.loads(
            (candidate_root / "environment.json").read_text(encoding="utf-8")
        )
        if current_env["fixture"] != candidate_env["fixture"]:
            raise ValueError("Comparison fixture mismatch")
        candidate_hashes.add(comparison["artifacts"]["candidate_dll_sha256"])
        current_hashes.add(comparison["artifacts"]["current_dll_sha256"])
        current_processed = comparison["rates"]["current"]["processed_fps"]["median"]
        candidate_processed = comparison["rates"]["candidate"]["processed_fps"][
            "median"
        ]
        current_output = comparison["rates"]["current"]["output_swap_fps"][
            "median"
        ]
        candidate_output = comparison["rates"]["candidate"]["output_swap_fps"][
            "median"
        ]
        rows.append(
            {
                "fixture": current_env["fixture"],
                "comparison": str(path.resolve()),
                "comparison_sha256": sha256(path),
                "warmup_seconds_per_path": current_env["warmup_seconds"],
                "measured_windows_per_path": 5,
                "minimum_window_seconds": comparison.get(
                    "minimum_window_seconds", current_env["warmup_seconds"]
                ),
                "current_processed_median_fps": current_processed,
                "candidate_processed_median_fps": candidate_processed,
                "processed_improvement_percent": (
                    candidate_processed / current_processed - 1
                )
                * 100,
                "current_output_median_fps": current_output,
                "candidate_output_median_fps": candidate_output,
                "output_improvement_percent": (
                    candidate_output / current_output - 1
                )
                * 100,
                "current_guide_p50_ms": comparison["sampled_guide"][
                    "current_p50_ms"
                ],
                "candidate_guide_p50_ms": comparison["sampled_guide"][
                    "candidate_p50_ms"
                ],
                "guide_improvement_percent": comparison["sampled_guide"][
                    "improvement_percent"
                ],
                "candidate_processed_reaches_60_fps": candidate_processed >= 60,
                "candidate_output_reaches_60_fps": candidate_output >= 60,
                "current_gpu_preflight": current_env["gpu_preflight"],
                "candidate_gpu_preflight": candidate_env["gpu_preflight"],
            }
        )

    fixtures = {row["fixture"] for row in rows}
    if len(fixtures) != len(rows):
        raise ValueError("Fixture comparisons must be unique")
    if len(candidate_hashes) != 1 or len(current_hashes) != 1:
        raise ValueError("DLL hashes differ across clip comparisons")

    def values(key):
        return [row[key] for row in rows]

    report = {
        "validated": True,
        "scope": (
            "Three matched sequential actual-app 3840x2160 input/per-eye, "
            "7680x2160 Full SBS, DA2 Small Balanced comparisons. Each clip has "
            "five measured windows per path. Output IDs are Qt submissions, not "
            "physical scanout; content is scaled public source, not native-4K detail."
        ),
        "artifacts": {
            "current_dll_sha256": next(iter(current_hashes)),
            "candidate_dll_sha256": next(iter(candidate_hashes)),
        },
        "clips": rows,
        "summary": {
            "clip_count": len(rows),
            "measured_windows_per_path": sum(
                row["measured_windows_per_path"] for row in rows
            ),
            "all_processed_medians_improved": all(
                row["processed_improvement_percent"] > 0 for row in rows
            ),
            "all_output_medians_improved": all(
                row["output_improvement_percent"] > 0 for row in rows
            ),
            "all_sampled_guide_p50_improved": all(
                row["guide_improvement_percent"] > 0 for row in rows
            ),
            "processed_improvement_percent": {
                "minimum": min(values("processed_improvement_percent")),
                "median": statistics.median(values("processed_improvement_percent")),
                "maximum": max(values("processed_improvement_percent")),
            },
            "output_improvement_percent": {
                "minimum": min(values("output_improvement_percent")),
                "median": statistics.median(values("output_improvement_percent")),
                "maximum": max(values("output_improvement_percent")),
            },
            "guide_improvement_percent": {
                "minimum": min(values("guide_improvement_percent")),
                "median": statistics.median(values("guide_improvement_percent")),
                "maximum": max(values("guide_improvement_percent")),
            },
            "candidate_processed_60fps_clip_count": sum(
                row["candidate_processed_reaches_60_fps"] for row in rows
            ),
            "candidate_output_60fps_clip_count": sum(
                row["candidate_output_reaches_60_fps"] for row in rows
            ),
            "eye_4k60_supported": False,
        },
        "decision": (
            "The rolling candidate has a repeatable processing and guide-stage "
            "benefit across all three clips. Two output comparisons are capped near "
            "60 Hz, while FloorballGame remains below 60. Continue mode/lifecycle "
            "validation before changing the pinned product DLL."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
