"""Sequential public-video output comparison with idle preflight and GPU log."""

import json
import argparse
import subprocess
import sys
import threading
import time
from pathlib import Path

from remeasure_live_gpu import sample


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=Path("out/live-gui-promotion/output")
    )
    parser.add_argument("--balanced-only", action="store_true")
    parser.add_argument("--live-modes-only", action="store_true")
    parser.add_argument("--poll-ms", type=int, choices=(1, 2, 4, 8))
    parser.add_argument("--hide-main", action="store_true")
    args = parser.parse_args()
    root = args.output
    root.mkdir(parents=True, exist_ok=True)
    cases = [
        ("balanced", 30, True),
        ("balanced", 30, False),
        ("balanced", 60, False),
        ("performance", 60, False),
        ("video-quality", 60, False),
    ]
    if args.balanced_only:
        cases = [("balanced", 60, False)]
    elif args.live_modes_only:
        cases = [
            (mode, 60, False) for mode in ("performance", "balanced", "video-quality")
        ]
    for mode, hz, legacy in cases:
        name = f"{mode}-{hz}" + ("-legacy" if legacy else "")
        target = root / name
        if (target / "summary.json").exists():
            continue
        idle = []
        consecutive = 0
        for _ in range(30):
            row = sample()
            idle.append(row)
            quiet = not row["returncode"] and float(row["csv"].split(",")[1]) <= 5
            consecutive = consecutive + 1 if quiet else 0
            if consecutive == 3:
                break
            time.sleep(1)
        if consecutive < 3:
            (root / f"{name}-idle-failed.json").write_text(json.dumps(idle, indent=2))
            raise RuntimeError("GPU idle gate failed; foreign work untouched")
        command = [
            sys.executable,
            "v1/benchmark_live_modes.py",
            "--output",
            str(target),
            "--sizes",
            "1920x1080",
            "--modes",
            mode,
            "--source",
            "FloorballGame",
            "--path",
            "gpu",
            "--hz",
            str(hz),
        ]
        if legacy:
            command.append("--legacy-poll")
        if args.poll_ms is not None:
            command.extend(("--poll-ms", str(args.poll_ms)))
        if args.hide_main:
            command.append("--hide-main")
        samples = []
        stop = threading.Event()

        def observe():
            while not stop.is_set():
                try:
                    samples.append(sample())
                except Exception as error:
                    samples.append(dict(error=str(error)))
                stop.wait(1)

        observer = threading.Thread(target=observe, daemon=True)
        observer.start()
        print("START", name, flush=True)
        try:
            with (root / f"{name}.log").open("w", encoding="utf-8") as log:
                run = subprocess.run(
                    command,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=180,
                )
        finally:
            stop.set()
            observer.join(timeout=12)
            (root / f"{name}-gpu.json").write_text(
                json.dumps(dict(idle=idle, during=samples), indent=2)
            )
        (root / f"{name}-command.json").write_text(
            json.dumps(dict(command=command, returncode=run.returncode), indent=2)
        )
        if run.returncode:
            raise RuntimeError(f"{name} failed; inspect retained log")
        subprocess.run(
            [sys.executable, "v1/summarize_live_modes.py", str(target)], check=True
        )
        print("DONE", name, flush=True)


if __name__ == "__main__":
    main()
