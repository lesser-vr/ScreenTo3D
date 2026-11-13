"""Rerun unchanged live paths with idle preflight and device-wide observation."""

import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

ROOT = Path("out/live-gpu-speed/recheck-idle-20260905")
QUERY = [
    "nvidia-smi",
    "--query-gpu=timestamp,utilization.gpu,utilization.memory,memory.used,power.draw,temperature.gpu,clocks.sm",
    "--format=csv,noheader,nounits",
]


def sample():
    result = subprocess.run(
        QUERY,
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
        timeout=10,
    )
    return dict(
        wall_ns=time.time_ns(),
        monotonic_ns=time.perf_counter_ns(),
        csv=result.stdout.strip(),
        error=result.stderr.strip(),
        returncode=result.returncode,
    )


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    manifest_path = ROOT / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else []
    for index, mode in enumerate(("performance", "balanced", "video-quality")):
        paths = (
            ("reference", "candidate") if index % 2 == 0 else ("candidate", "reference")
        )
        for path in paths:
            if any(
                r["mode"] == mode and r["path"] == path and r["returncode"] == 0
                for r in manifest
            ):
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
                (ROOT / "idle-preflight-failed.json").write_text(
                    json.dumps(idle, indent=2)
                )
                raise RuntimeError(
                    "GPU not idle at preflight; do not stop foreign workloads"
                )
            target = ROOT / f"{mode}-{path}"
            env = os.environ.copy()
            env["SCREENTO3D_LIVE_GPU_CANDIDATE"] = str(int(path == "candidate"))
            command = [
                sys.executable,
                "v1/benchmark_live_modes.py",
                "--output",
                str(target),
                "--sizes",
                "1920x1080",
                "--modes",
                mode,
                "--seconds",
                "6",
                "--repeats",
                "5",
            ]
            samples = []
            stopped = threading.Event()

            def observe():
                while not stopped.is_set():
                    try:
                        samples.append(sample())
                    except Exception as error:
                        samples.append(dict(wall_ns=time.time_ns(), error=str(error)))
                    stopped.wait(1)

            observer = threading.Thread(target=observe, daemon=True)
            observer.start()
            print(f"START {mode} {path}", flush=True)
            try:
                with (ROOT / f"{mode}-{path}.log").open("w", encoding="utf-8") as log:
                    run = subprocess.run(
                        command,
                        env=env,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                        timeout=180,
                    )
            finally:
                stopped.set()
                observer.join(timeout=12)
                (ROOT / f"{mode}-{path}-gpu.json").write_text(
                    json.dumps(dict(idle=idle, during=samples), indent=2)
                )
            entry = dict(
                mode=mode, path=path, command=command, returncode=run.returncode
            )
            manifest.append(entry)
            (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2))
            if run.returncode:
                raise RuntimeError(f"{mode} {path} failed; retained log")
            subprocess.run(
                [sys.executable, "v1/summarize_live_modes.py", str(target)], check=True
            )
            print(f"DONE {mode} {path}", flush=True)


if __name__ == "__main__":
    main()
