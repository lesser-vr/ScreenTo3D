"""Bounded standalone Qt/CUDA display check, with isolated SDK and raw evidence."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=Path("out/qt-texture-probe/verified")
    )
    parser.add_argument("--ipc", action="store_true")
    parser.add_argument("--crash-worker", action="store_true")
    parser.add_argument("--public-video", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    build = root / "out/qt-texture-probe"
    sdk = root / "out/qt-sdk/6.10.2/msvc2022_64"
    env = os.environ.copy()
    env.update(
        PATH=str(sdk / "bin") + os.pathsep + env["PATH"],
        QT_PLUGIN_PATH=str(sdk / "plugins"),
        QSG_RHI_BACKEND="d3d11",
        QT_D3D_NO_VBLANK_THREAD="1",
    )
    if args.public_video:
        if not args.ipc:
            raise ValueError("Public-video producer requires --ipc")
        env["SCREENTO3D_TEXTURE_PUBLIC"] = "1"
        env["SCREENTO3D_TEXTURE_PYTHON"] = sys._base_executable
        env["PYTHONPATH"] = os.pathsep.join(
            str(root / path)
            for path in (
                "v1",
                "out/gui-python-deps",
                "out/capture-python-deps",
                "out/v1-python-deps",
                "out/qt-build-deps",
            )
        )
    else:
        env.pop("SCREENTO3D_TEXTURE_PUBLIC", None)
    if args.crash_worker:
        if not args.ipc:
            raise ValueError("Worker fault injection requires --ipc")
        env["SCREENTO3D_TEXTURE_TEST_CRASH"] = "1"
    else:
        env.pop("SCREENTO3D_TEXTURE_TEST_CRASH", None)
    executable = build / (
        "qt_texture_ipc_probe.exe" if args.ipc else "qt_texture_probe.exe"
    )
    source_dll = build / (
        "qt_texture_ipc_source.dll" if args.ipc else "qt_texture_source.dll"
    )
    import psutil

    process = subprocess.Popen(
        [str(executable), str(output)],
        cwd=root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    owned_children = {}
    deadline = time.monotonic() + 30
    while process.poll() is None:
        try:
            for child in psutil.Process(process.pid).children(recursive=True):
                owned_children[child.pid] = child.create_time()
        except psutil.NoSuchProcess:
            pass
        if time.monotonic() >= deadline:
            process.kill()
            raise TimeoutError("Owned Qt texture test exceeded 30 seconds")
        time.sleep(0.02)
    stdout, stderr = process.communicate()
    (output / "stdout.jsonl").write_text(stdout, encoding="utf-8")
    (output / "stderr.txt").write_text(stderr, encoding="utf-8")
    remaining = []
    for pid, created in owned_children.items():
        try:
            child = psutil.Process(pid)
            if child.create_time() == created:
                try:
                    child.wait(timeout=3)
                except psutil.TimeoutExpired:
                    remaining.append(pid)
        except psutil.NoSuchProcess:
            pass
    rows = [json.loads(line) for line in stdout.splitlines() if line.startswith("{")]
    expected_outcome = (
        process.returncode == 2 and "Child response failed" in stderr
        if args.crash_worker
        else process.returncode == 0 and bool(rows) and rows[-1].get("passed", False)
    )
    report = dict(
        returncode=process.returncode,
        rows=rows,
        passed=expected_outcome and not remaining,
        injected_worker_crash=args.crash_worker,
        owned_child_count=len(owned_children),
        remaining_owned_children=remaining,
        executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
        source_dll_sha256=hashlib.sha256(source_dll.read_bytes()).hexdigest(),
        cross_process=args.ipc,
        public_video=args.public_video,
        public_worker_sha256=hashlib.sha256(
            (root / "v1/texture_public_worker.py").read_bytes()
        ).hexdigest()
        if args.public_video
        else None,
        publish_dll_sha256=hashlib.sha256(
            (root / "out/live-texture-publish/live_texture_publish.dll").read_bytes()
        ).hexdigest()
        if args.public_video
        else None,
        qt_version="6.10.2",
        qt_d3d_no_vblank_thread=1,
        note="Synthetic display/lifecycle only; not live application throughput or device loss",
    )
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(stdout)
    print(stderr)
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "owned_child_count": len(owned_children),
                "remaining_owned_children": remaining,
            }
        )
    )
    assert report["passed"], "Standalone Qt texture check failed"


if __name__ == "__main__":
    main()
