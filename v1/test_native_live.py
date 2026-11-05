"""Actual desktop native-delivery lifecycle, using only an owned public source."""

import argparse
import json
import os
from pathlib import Path
import sys
import time

import numpy as np
import shiboken6
from PySide6.QtGui import QImage, QWindow, QGuiApplication
from PySide6.QtCore import QObject, Qt
from PySide6.QtTest import QTest

from benchmark_live_modes import ClockOracle, memory_bytes
from depthsbs_app.desktop import create_app
from depthsbs_app.capture_mailbox import WIDTH


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--hz", type=int, choices=(0, 30, 60), default=0)
    parser.add_argument("--mode", choices=("performance", "balanced"), default="performance")
    parser.add_argument("--default-path", action="store_true")
    parser.add_argument("--cycle-screens", action="store_true")
    parser.add_argument("--steady-seconds", type=int, default=5)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    app, engine, desktop = create_app()
    desktop.main_window.resize(980, 700)
    desktop.main_window.setPosition(0, 0)
    oracle = ClockOracle("FloorballGame")
    oracle.show()
    live = desktop.live
    if args.default_path:
        assert live.processingPath == 'gpu-texture' and not live.nativeReady
    live.output_placement.path = args.output / "placement.json"

    def pump(seconds=0.1):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            app.processEvents()
            time.sleep(0.003)

    def wait(predicate, seconds=120):
        until = time.monotonic() + seconds
        while not predicate() and time.monotonic() < until:
            pump(0.03)
            if not live.active and live.started:
                break
        assert predicate(), (live.status, live.native.report() if live.native else None)

    def native():
        return live.native.report()

    try:
        pump(0.3)
        live.items = [
            dict(
                kind="window",
                id=int(oracle.winId()),
                pid=os.getpid(),
                label=oracle.windowTitle(),
                width=round(oracle.width() * oracle.devicePixelRatioF()),
                height=round(oracle.height() * oracle.devicePixelRatioF()),
            )
        ]
        live.selected = 0
        live.setSbs(True)
        live.setMode(args.mode)
        # The minimal shell has one output consumer and no in-app preview.
        if not args.default_path:
            live.setProcessingPath("gpu-texture")
        assert live.processingPath == "gpu-texture", live.status
        assert desktop.main_window.findChild(QObject, 'liveProcessingPath').property('currentIndex') == 2
        live.setPresentationHz(args.hz)
        live.startSbs(0, 0)
        wait(lambda: native()["output"]["submitted_frames"] >= 5)
        assert native()["main"]["submitted_frames"] == 0
        assert live.mailbox.pixels is None and live.provider.image.isNull()
        live.setProcessingPath("gpu")
        assert live.processingPath == "gpu-texture"
        assert not desktop.main_window.findChild(
            QObject, "liveProcessingPath"
        ).property("enabled")
        live.showOutput(0, False)
        wait(lambda: native()["output"]["submitted_frames"] >= 5)
        image = live.output_window.grabWindow().convertToFormat(QImage.Format_RGB888)
        pixels = np.frombuffer(image.bits(), np.uint8).reshape(
            image.height(), image.bytesPerLine()
        )
        rgb = pixels[:, : image.width() * 3].reshape(image.height(), image.width(), 3)
        half = image.width() // 2
        differences = int(np.count_nonzero(rgb[:, :half] != rgb[:, half : half * 2]))
        assert differences > 100
        assert image.save(str(args.output / "output-window.png"))
        begin = native()
        start = time.perf_counter()
        processed = live._stats()[0]
        steady_memory = []
        for _ in range(max(5, args.steady_seconds)):
            pump(1)
            assert live.active, live.status
            steady_memory.append(dict(gui=memory_bytes(os.getpid()),worker=memory_bytes(live.process.pid)))
            assert native()['live_pools'] == native()['live_nodes'] == 1
        elapsed = time.perf_counter() - start
        after = native()
        rates = dict(
            seconds=elapsed,
            processed=(live._stats()[0] - processed) / elapsed,
            main=(after["main"]["submitted_frames"] - begin["main"]["submitted_frames"])
            / elapsed,
            output=(
                after["output"]["submitted_frames"]
                - begin["output"]["submitted_frames"]
            )
            / elapsed,
        )
        desktop.main_window.hide()
        pump(0.2)
        hidden = native()
        wait(
            lambda: native()["output"]["submitted_frames"]
            > hidden["output"]["submitted_frames"] + 5
        )
        assert (
            native()["main"]["submitted_frames"] == hidden["main"]["submitted_frames"]
        )
        live.output_window.hide()
        pump(0.2)
        both = native()
        count = live._stats()[0]
        pump(0.5)
        assert live._stats()[0] > count
        assert native()["main"]["submitted_frames"] == both["main"]["submitted_frames"]
        assert (
            native()["output"]["submitted_frames"] == both["output"]["submitted_frames"]
        )
        desktop.main_window.showNormal()
        live.showOutput(0, False)
        wait(
            lambda: native()["output"]["submitted_frames"]
            > both["output"]["submitted_frames"] + 3
        )
        desktop.main_window.setProperty("page", 2)
        pump(0.2)
        page = native()
        pump(0.3)
        assert native()["main"]["submitted_frames"] == page["main"]["submitted_frames"]
        desktop.main_window.setProperty("page", 0)
        assert native()["main"]["submitted_frames"] == 0
        live.showOutput(0, True)
        pump(0.3)
        assert (
            live.output_excluded
            and live.output_window.visibility() == QWindow.FullScreen
        )
        QTest.keyClick(live.output_window, Qt.Key_Escape)
        pump(0.2)
        assert live.output_window.visibility() != QWindow.FullScreen
        oracle.resize(400, 280)
        expected_width = round(400 * oracle.devicePixelRatioF()) * 2
        wait(lambda: live.meta[WIDTH] == expected_width and live.native.has_frame,
             120 if live.stereo_renderer == 'rowflow-sym' else 20)
        first_resized_sequence = live.native.last_sequence
        wait(lambda: native()["output"]["last_submitted_id"] >= first_resized_sequence)
        wait(lambda: native()["live_pools"] == 1, 10)
        assert native()["live_nodes"] == 1
        assert live._stats()[2] > 1
        screen_checks = []
        if args.cycle_screens:
            for screen in QGuiApplication.screens():
                area = screen.availableGeometry()
                live.output_window.setScreen(screen)
                live.output_window.resize(min(800, area.width()), min(450, area.height()))
                live.output_window.setPosition(area.x()+20, area.y()+20)
                pump(.3)
                previous = native()['output']['submitted_frames']
                wait(lambda: native()['output']['submitted_frames'] > previous+10, 15)
                assert live.output_window.screen() == screen
                screen_checks.append(dict(width=area.width(),height=area.height(),continued=True))
        assert desktop.main_window.grabWindow().save(str(args.output / "gui.png"))
        report = live.report()
        assert report["shared_pixel_bytes"] == 0
        assert report["qt_delivery"]["provider_requests"] == 0
        assert not any(
            name == "cuda" or name.startswith("cuda.") for name in sys.modules
        )
        live.stop()
        assert not live.hasFrame and desktop.lease.owner == "live"
        pump(0.15)
        assert not live.output_window.isVisible()
        wait(lambda: not live.active, 15)
        assert desktop.lease.owner is None
        pump(0.15)
        assert native()["live_pools"] == native()["live_nodes"] == 0
        live.startSbs(0, 0)
        wait(lambda: native()["output"]["submitted_frames"] >= 2)
        oracle.showMinimized()
        wait(lambda: not live.active, 15)
        assert not live.hasFrame and desktop.lease.owner is None
        oracle.showNormal()
        pump(0.2)
        live.startSbs(0, 0)
        wait(lambda: native()["output"]["submitted_frames"] >= 2)
        live.process.terminate()
        wait(lambda: not live.active, 15)
        pump(0.2)
        assert not live.hasFrame and desktop.lease.owner is None
        assert native()["live_pools"] == native()["live_nodes"] == 0
        cancel_errors = []
        live.errorOccurred.connect(cancel_errors.append)
        live.startSbs(0, 0)
        assert live.active and not live.hasFrame
        live.stop()
        wait(lambda: not live.active, 15)
        pump(.2)
        assert not cancel_errors, cancel_errors
        assert desktop.lease.owner is None and not live.hasFrame
        assert native()["live_pools"] == native()["live_nodes"] == 0
        report.update(
            passed=True,
            measured_interval=rates,
            steady_memory=steady_memory,
            eyes_distinct=differences,
            hidden_and_restore=True,
            page_restore=True,
            resize=True,
            stop_clear=True,
            restart_source_loss=True,
            worker_crash=True,
            preparation_cancel=True,
            fullscreen_escape=True,
            capture_exclusion=True,
            screen_transitions=screen_checks,
            scope="Actual native desktop lifecycle; rates are short exploratory Qt submission counts",
        )
        (args.output / "report.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        print(
            json.dumps(
                {"passed": True, "rates": rates, "native": report["native_delivery"]}
            )
        )
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
