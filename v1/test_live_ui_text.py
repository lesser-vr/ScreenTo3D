"""Compare actual application static UI pixels across delivery and redraws."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import time

import numpy as np
import shiboken6
from PySide6.QtGui import QImage

from benchmark_live_modes import ClockOracle
from screento3d_app.desktop import create_app


def pixels(image):
    image = image.convertToFormat(QImage.Format_RGBA8888)
    return (
        np.frombuffer(image.bits(), np.uint8)
        .reshape(image.height(), image.bytesPerLine())
        .copy()
    )


def difference(actual, expected):
    delta = np.abs(actual.astype(np.int16) - expected.astype(np.int16))
    return dict(
        changed_channels=int(np.count_nonzero(delta)),
        maximum_channel_delta=int(delta.max()),
        channels_over_one=int(np.count_nonzero(delta > 1)),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--path", choices=("gpu", "gpu-texture"), required=True)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--host-first", action="store_true")
    parser.add_argument("--selection-only", action="store_true")
    parser.add_argument("--historical", type=Path, action="append", default=[])
    parser.add_argument("--hz", type=int, choices=(30, 60), default=30)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    app, engine, desktop = create_app()
    window = desktop.main_window
    window.resize(980, 700)
    window.setPosition(0, 0)
    oracle = ClockOracle("FloorballGame")
    oracle.resize(480, 320)
    oracle.show()
    live = desktop.live

    def pump(seconds=0.1):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            time.sleep(0.003)

    def wait(predicate):
        end = time.monotonic() + 120
        while not predicate() and time.monotonic() < end:
            pump()
        assert predicate(), live.status

    rows = []
    try:
        pump(0.3)
        live.items = [
            dict(
                kind="window",
                id=int(oracle.winId()),
                pid=os.getpid(),
                label=oracle.windowTitle(),
                width=720,
                height=480,
            )
        ]
        live.selected = 0
        live.setSbs(True)
        if args.host_first:
            assert args.reference is None
            live.setProcessingPath("gpu")
            live.setPresentationHz(args.hz)
            if not args.selection_only:
                live.start()
                wait(lambda: live._stats()[0] >= 15)
                live.showOutput(0, False)
            pump(1)
            args.reference = args.output / "host-reference.png"
            assert window.grabWindow().save(str(args.reference))
            live.stop()
            wait(lambda: not live.active)
        live.setProcessingPath(args.path)
        assert live.processingPath == args.path, live.status
        live.setPresentationHz(args.hz)
        if not args.selection_only:
            live.start()
            wait(lambda: live._stats()[0] >= 15)
            live.showOutput(0, False)
        pump(1)
        # The top 250 logical rows contain the real title, navigation, mode,
        # source and strength controls. The path/rate row and video are below.
        # Those intentionally different/dynamic regions are never compared.
        height = round(250 * window.devicePixelRatio())
        baseline = window.grabWindow()
        assert not baseline.isNull()
        assert baseline.save(str(args.output / "baseline.png"))
        expected = pixels(baseline)[:height]
        reference = None
        if args.reference:
            reference_image = QImage(str(args.reference))
            assert not reference_image.isNull()
            assert reference_image.size() == baseline.size()
            reference = pixels(reference_image)[:height]
        for index in range(12):
            action = ("redraw", "hide_restore", "page_restore", "resize_restore")[
                index % 4
            ]
            if action == "hide_restore":
                window.hide()
                live.output_window.hide()
                pump(0.2)
                window.show()
                if not args.selection_only:
                    live.showOutput(0, False)
            elif action == "page_restore":
                window.setProperty("page", 1)
                pump(0.2)
                window.setProperty("page", 0)
            elif action == "resize_restore":
                window.resize(1100, 760)
                pump(0.2)
                window.resize(980, 700)
            window.update()
            pump(0.4)
            actual = window.grabWindow()
            assert actual.size() == baseline.size()
            assert actual.save(str(args.output / f"capture-{index:02d}.png"))
            values = pixels(actual)[:height]
            rows.append(
                dict(
                    index=index,
                    action=action,
                    changed_channels=int(np.count_nonzero(values != expected)),
                    reference_difference=difference(values, reference)
                    if reference is not None
                    else None,
                    reference_changed_channels=(
                        int(np.count_nonzero(values != reference))
                        if reference is not None
                        else None
                    ),
                )
            )
        historical = []
        if args.selection_only:
            assert not live.active and live._stats()[0] == 0
            if live.native:
                assert live.native.report()["live_nodes"] == 0
                assert live.native.report()["live_pools"] == 0
        for path in args.historical:
            old = QImage(str(path))
            assert reference is not None and old.size() == baseline.size()
            historical.append(
                dict(
                    path=str(path),
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    **difference(pixels(old)[:height], reference),
                )
            )
        report = dict(
            stable_redraw_passed=all(row["changed_channels"] == 0 for row in rows),
            reference_exact=all(
                row["reference_changed_channels"] in (None, 0) for row in rows
            ),
            passed=all(
                row["changed_channels"] == 0
                and (
                    row["reference_difference"] is None
                    or row["reference_difference"][
                        "changed_channels" if args.host_first else "channels_over_one"
                    ]
                    == 0
                )
                for row in rows
            )
            and all(row["channels_over_one"] == 0 for row in historical),
            path=args.path,
            hz=args.hz,
            dpr=window.devicePixelRatio(),
            physical_header_height=height,
            reference_channel_tolerance=0 if args.host_first else 1,
            same_process_host_reference=args.host_first,
            selection_only=args.selection_only,
            reference_tolerance_reason="Independent host/host runs differ by at most one 8-bit level; same-session redraw must remain exact",
            reference_sha256=hashlib.sha256(args.reference.read_bytes()).hexdigest()
            if args.reference
            else None,
            historical=historical,
            cases=rows,
            script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            live=live.report(),
            scope="Actual Main.qml static top 250 logical rows; not whole-UI or physical-display validation",
        )
        (args.output / "report.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        print(
            json.dumps({key: report[key] for key in ("passed", "path", "cases")}),
            flush=True,
        )
        assert report["passed"], "Actual application static UI pixels changed"
    finally:
        live.stop()
        until = time.monotonic() + 15
        while live.active and time.monotonic() < until:
            pump()
        oracle.close()
        if oracle.video is not None:
            oracle.video.release()
        shiboken6.delete(engine)


if __name__ == "__main__":
    main()
