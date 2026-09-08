"""Same generated desktop oracle for WGC and DXGI; FFmpeg reference inventory/run."""

import argparse
import json
import csv
import platform
import importlib.metadata
import multiprocessing as mp
import subprocess
import time
from collections import deque
from pathlib import Path


def decode_stamp(array, x, y, scale):
    bits = []
    for bit in range(48):
        pixel = array[int(y + 4 * scale), int(x + (bit * 6 + 3) * scale), :3]
        bits.append(bool((pixel > 200).all()))
    return sum(1 << bit for bit, enabled in enumerate(bits) if enabled)


def dxgi_measure(pipe, seconds, x, y, scale):
    try:
        from depthsbs_app.capture_sources import enable_capture_dpi

        enable_capture_dpi()
        import numpy as np
        from windows_capture import DxgiDuplicationSession

        session = DxgiDuplicationSession(1)
        values = deque(maxlen=512)
        durations = deque(maxlen=512)
        start = time.perf_counter()
        count = 0
        shape = None
        while time.perf_counter() - start < seconds:
            before = time.perf_counter_ns()
            frame = session.acquire_frame(timeout_ms=16)
            if frame is not None:
                image = np.array(frame.to_numpy(), copy=True)
                durations.append((time.perf_counter_ns() - before) / 1e6)
                stamp = decode_stamp(image, x, y, scale)
                age = time.perf_counter_ns() / 1e6 - stamp
                if 0 <= age < 1000:
                    values.append(age)
                count += 1
                shape = list(image.shape)
        del session
        pipe.send(
            dict(
                api="DXGI duplication",
                frames=count,
                seconds=time.perf_counter() - start,
                paint_to_readback_ms=list(values),
                acquire_wait_and_copy_ms=list(durations),
                shape=shape,
                cursor="No cursor option in this adapter; not chosen for product",
            )
        )
    except Exception as error:
        pipe.send(dict(api="DXGI duplication", error=str(error)))
    finally:
        pipe.close()


def main():
    from depthsbs_app.desktop import create_app
    from test_live_preview import Oracle
    import shiboken6
    from depthsbs_app.desktop_jobs import BUNDLE

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    app, engine, desktop = create_app()
    window = engine.rootObjects()[0]
    window.setPosition(0, 0)
    window.resize(980, 700)
    oracle = Oracle()
    oracle.show()

    def pump(seconds):
        until = time.perf_counter() + seconds
        while time.perf_counter() < until:
            app.processEvents()
            time.sleep(0.003)

    pump(0.5)
    live = desktop.live
    live.setKind("monitor")
    assert len(live.items) == 1, (
        "This benchmark is bounded to the single reference monitor"
    )
    live.start()
    deadline = time.perf_counter() + 15
    while live.submitted < 5 and live.active and time.perf_counter() < deadline:
        pump(0.05)
    assert live.active and live.submitted >= 5, live.status
    scale = oracle.devicePixelRatioF()
    x, y = oracle.x() * scale, oracle.y() * scale
    ages = []
    last = -1
    start = time.perf_counter()
    while time.perf_counter() - start < 5:
        pump(0.02)
        if live.version == last:
            continue
        last = live.version
        image = live.provider.image
        stamp = 0
        for bit in range(48):
            color = image.pixelColor(int(x + (bit * 6 + 3) * scale), int(y + 4 * scale))
            if color.red() > 200 and color.green() > 200 and color.blue() > 200:
                stamp |= 1 << bit
        age = time.perf_counter_ns() / 1e6 - stamp
        if 0 <= age < 1000:
            ages.append(age)
    assert len(ages) > 10, "Oracle timestamp was not recovered"
    report = {
        "wgc": live.report(),
        "wgc_paint_to_gui_sample_ms": ages,
        "monitor_count": len(live.items),
        "scale": scale,
    }
    live.stop()
    deadline = time.perf_counter() + 10
    while live.active and time.perf_counter() < deadline:
        pump(0.05)
    assert not live.active
    context = mp.get_context("spawn")
    receive, send = context.Pipe(False)
    child = context.Process(target=dxgi_measure, args=(send, 5, x, y, scale))
    child.start()
    send.close()
    deadline = time.perf_counter() + 15
    while not receive.poll() and time.perf_counter() < deadline:
        pump(0.03)
    if not receive.poll():
        child.terminate()
        child.join(5)
        raise RuntimeError("DXGI comparison timed out")
    report["dxgi"] = receive.recv()
    child.join(5)
    assert not child.is_alive()
    child.close()
    receive.close()
    command = [
        str(BUNDLE / "ffmpeg/ffmpeg.exe"),
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "ddagrab=output_idx=0:framerate=30:draw_mouse=0:dup_frames=0",
        "-vf",
        "hwdownload,format=bgra",
        "-t",
        "5",
        "-progress",
        "pipe:1",
        "-f",
        "null",
        "-",
    ]
    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    deadline = time.perf_counter() + 15
    while proc.poll() is None and time.perf_counter() < deadline:
        pump(0.03)
    if proc.poll() is None:
        proc.kill()
    stdout, stderr = proc.communicate(timeout=5)
    report["ffmpeg"] = dict(
        exit_code=proc.returncode,
        progress=stdout.decode(),
        error=stderr.decode(),
        scope="DXGI ddagrab source + CPU download + null sink; no pixel file",
    )
    assert report["ffmpeg"]["exit_code"] == 0

    def summary(values):
        v = sorted(values)
        return (
            {f"p{q}": v[int((len(v) - 1) * q / 100)] for q in (50, 95, 99)}
            if v
            else None
        )

    report["summary"] = dict(
        wgc_paint_to_gui_ms=summary(ages),
        dxgi_paint_to_readback_ms=summary(
            report["dxgi"].get("paint_to_readback_ms", [])
        ),
        caution="Different endpoints: GUI handoff vs child readback. Not motion-to-photon or SBS performance.",
    )
    from depthsbs_app.capture_color import display_colors

    report["environment"] = dict(
        os=platform.platform(),
        python=platform.python_version(),
        qt=importlib.metadata.version("PySide6"),
        capture=importlib.metadata.version("windows-capture"),
        display_color=display_colors(),
        gpu=subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=10,
        ).stdout.strip(),
        commit=subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=10,
        ).stdout.strip(),
        dirty=bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=10,
            ).stdout.strip()
        ),
    )
    (args.output / "report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    with (args.output / "latency.csv").open(
        "w", newline="", encoding="utf-8"
    ) as output:
        writer = csv.writer(output)
        writer.writerow(["boundary", "sample", "milliseconds"])
        for label, values in [
            ("wgc_paint_to_gui_sample", ages),
            ("dxgi_paint_to_readback", report["dxgi"].get("paint_to_readback_ms", [])),
        ]:
            writer.writerows(
                (label, index, value) for index, value in enumerate(values)
            )
    print(json.dumps(report["summary"]))
    oracle.close()
    window.hide()
    shiboken6.delete(engine)


if __name__ == "__main__":
    main()
