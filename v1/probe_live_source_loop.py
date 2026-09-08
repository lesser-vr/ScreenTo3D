"""Owned source-only event-loop probe. No capture or depth worker is started."""

import argparse
import json
import os
from pathlib import Path
import time

import numpy as np
import shiboken6
from PySide6.QtWidgets import QApplication

from benchmark_live_modes import ClockOracle
from depthsbs_app.desktop import create_app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--shell", action="store_true")
    parser.add_argument("--two-windows", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Output must be new")
    if args.two_windows and not args.shell:
        raise ValueError("Two windows requires the product shell")
    engine = None
    if args.shell:
        app, engine, desktop = create_app()
        assert not desktop.live.active
    else:
        app = QApplication([])
    source = ClockOracle("FloorballGame")
    source.resize(
        round(1920 / source.devicePixelRatioF()),
        round(1080 / source.devicePixelRatioF()),
    )
    source.show()
    if args.two_windows:
        desktop.live.output_window.show()
        source.timer.timeout.connect(desktop.main_window.update)
        source.timer.timeout.connect(desktop.live.output_window.update)
    try:
        rows = []
        for _ in range(3):
            start = time.perf_counter()
            cpu = time.process_time()
            before = source.sequence, source.paint_count
            intervals = []
            while time.perf_counter() - start < 3:
                began = time.perf_counter()
                app.processEvents()
                intervals.append((time.perf_counter() - began) * 1000)
                time.sleep(0.002)
            seconds = time.perf_counter() - start
            rows.append(
                dict(
                    seconds=seconds,
                    advance_fps=(source.sequence - before[0]) / seconds,
                    paint_fps=(source.paint_count - before[1]) / seconds,
                    cpu_cores=(time.process_time() - cpu) / seconds,
                    process_events_ms={
                        f"p{q}": float(np.percentile(intervals, q))
                        for q in (50, 95, 99)
                    },
                )
            )
        report = dict(
            shell=args.shell,
            two_windows=args.two_windows,
            rows=rows,
            qt_no_vblank=os.environ.get("QT_D3D_NO_VBLANK_THREAD"),
            qsg_no_vsync=os.environ.get("QSG_NO_VSYNC"),
            qsg_render_loop=os.environ.get("QSG_RENDER_LOOP"),
            scope="Owned public source; no depth/capture worker; first window includes warmup; not physical display throughput",
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
        print(json.dumps(report))
    finally:
        source.close()
        source.video.release()
        if engine is not None:
            shiboken6.delete(engine)


if __name__ == "__main__":
    main()
