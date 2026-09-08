"""Run the standalone native texture probe, retaining raw output and provenance."""

import hashlib
import argparse
import json
import platform
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path("out/live-texture-handoff")
    executable = (root / "texture_handoff_probe.exe").resolve()
    root = args.output or root
    root.mkdir(parents=True, exist_ok=True)
    gpu = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=name,driver_version,utilization.gpu,memory.used",
            "--format=csv,noheader",
        ],
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    ).strip()
    run = subprocess.run(
        [str(executable)],
        capture_output=True,
        text=True,
        timeout=120,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    (root / "stdout.jsonl").write_text(run.stdout, encoding="utf-8")
    (root / "stderr.txt").write_text(run.stderr, encoding="utf-8")
    rows = [
        json.loads(line) for line in run.stdout.splitlines() if line.startswith("{")
    ]
    report = dict(
        command=[str(executable)],
        returncode=run.returncode,
        gpu=gpu,
        os=platform.platform(),
        rows=rows,
        exe_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
        passed=run.returncode == 0 and bool(rows) and rows[-1].get("passed", False),
        note="Synthetic two-device single-process handoff; readback outside timing, not live fps",
    )
    (root / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(run.stdout)
    print(run.stderr)
    assert report["passed"], "Texture handoff failed; app path unchanged"


if __name__ == "__main__":
    main()
