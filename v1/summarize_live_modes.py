import argparse
import json
from pathlib import Path
import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    rows = json.loads((args.directory / "runs.json").read_text())
    groups = []
    for size, mode in dict.fromkeys((r["size"], r["mode"]) for r in rows):
        selected = [r for r in rows if (r["size"], r["mode"]) == (size, mode)]
        fps = [r["output_swap_fps"] for r in selected]
        processing = [r["processed_fps"] for r in selected]
        memory = [sample[1] / 1024**2 for r in selected for sample in r["memory"]]
        last = selected[-1]
        target = last["report"].get("presentation_target_hz", 30)
        groups.append(
            dict(
                size=size,
                mode=mode,
                repeats=len(selected),
                output_fps_median=float(np.median(fps)),
                output_fps_range=[min(fps), max(fps)],
                processing_fps_median=float(np.median(processing)),
                memory_private_mib_range=[min(memory), max(memory)],
                first_last_window_median_delta_mib=float(
                    np.median([s[1] for s in last["memory"]])
                    - np.median([s[1] for s in selected[0]["memory"]])
                )
                / 1024**2,
                clock_samples=len(last.get("paint_to_output_readback_ms", [])),
                clock_attempts=last.get("clock_attempts"),
                clock_summary_ms=last.get("clock_summary_ms"),
                overload=last.get("overload"),
                local_30hz_candidate=len(selected) >= 5 and min(fps) >= 28.5,
                presentation_target_hz=target,
                local_target_candidate=len(selected) >= 5 and min(fps) >= target * 0.95,
                note="Local source window only; 5% cadence tolerance. Not quality approval, photon latency or leak freedom.",
            )
        )
    (args.directory / "summary.json").write_text(json.dumps(groups, indent=2))
    print(json.dumps(groups, indent=2))


if __name__ == "__main__":
    main()
