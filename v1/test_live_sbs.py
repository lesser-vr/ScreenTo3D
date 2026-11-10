"""Live SBS lifecycle oracle. Save only the owned public/generated test window."""

import json
import os
import time
from pathlib import Path

import numpy as np
import shiboken6
from PySide6.QtCore import Qt, QObject
from PySide6.QtTest import QTest
from PySide6.QtGui import QImage, QWindow

from benchmark_live_modes import ClockOracle
from depthsbs_app.desktop import create_app


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--hd", action="store_true")
    parser.add_argument("--hz", type=int, choices=(30, 60), default=30)
    parser.add_argument("--path", choices=("gpu", "reference"))
    parser.add_argument("--expect-path", choices=("gpu", "reference"))
    parser.add_argument(
        "--source", choices=("FloorballGame", "generated"), default="FloorballGame"
    )
    parser.add_argument(
        "--mode",
        default="balanced",
        choices=("performance", "balanced", "video-quality"),
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    app, engine, desktop = create_app()
    desktop.main_window.setPosition(0, 0)
    desktop.main_window.resize(980, 700)
    desktop.main_window.raise_()
    if args.source != "generated":
        from public_test_media import prepare

        prepare()
    oracle = ClockOracle(args.source)
    if args.hd:
        oracle.resize(1280, 720)
    oracle.show()
    live = desktop.live
    raw_swaps = [0]
    desktop.main_window.frameSwapped.connect(
        lambda: raw_swaps.__setitem__(0, raw_swaps[0] + 1)
    )

    def pump(seconds):
        end = time.perf_counter() + seconds
        while time.perf_counter() < end:
            app.processEvents()
            time.sleep(0.005)

    def wait(predicate, seconds=120):
        end = time.perf_counter() + seconds
        while not predicate() and time.perf_counter() < end:
            pump(0.03)
            if not live.active and live.started:
                break
        assert predicate(), live.status

    try:
        pump(0.5)
        width = round(oracle.width() * oracle.devicePixelRatioF())
        height = round(oracle.height() * oracle.devicePixelRatioF())
        live.items = [
            dict(
                kind="window",
                id=int(oracle.winId()),
                pid=os.getpid(),
                label=oracle.windowTitle(),
                width=width,
                height=height,
            )
        ]
        live.selected = 0
        live.setSbs(True)
        live.setMode(args.mode)
        live.setPresentationHz(args.hz)
        if args.path:
            live.setProcessingPath(args.path)
        selected_path = live.processingPath
        if args.expect_path:
            assert selected_path == args.expect_path, (
                "Unexpected GUI processing default"
            )
        live.setStrength(1.25)
        live.start()
        wait(lambda: live.submitted >= 5)
        for name in ("liveProcessingPath", "livePresentationHz"):
            picker = desktop.main_window.findChild(QObject, name)
            assert picker is not None and not picker.property("enabled")
        live.setPresentationHz(30 if args.hz == 60 else 60)
        live.setProcessingPath("reference" if selected_path == "gpu" else "gpu")
        assert live.presentationHz == args.hz and live.processingPath == selected_path
        assert (
            desktop.main_window.findChild(QObject, "livePolicy").property(
                "currentValue"
            )
            == args.mode
        )
        live.setMode("video-quality" if args.mode != "video-quality" else "performance")
        assert live.liveMode == args.mode, "active mode must remain immutable"
        live.setStrength(0.25)
        assert live.depthStrength == 1.25, "session strength must be immutable"
        image = live.provider.image.convertToFormat(QImage.Format_RGB888)
        assert (image.width(), image.height()) == (width * 2, height)
        rgb = (
            np.frombuffer(image.bits(), np.uint8)
            .reshape(image.height(), image.bytesPerLine())[:, : image.width() * 3]
            .reshape(image.height(), image.width(), 3)
        )
        difference = int(np.count_nonzero(rgb[:, :width] != rgb[:, width:]))
        assert difference > 100, "eyes must not be duplicated"
        assert image.save(str(args.output / "test-sbs.png"))
        first_count = live._stats()[0]
        timed_start = time.perf_counter()
        pump(5)
        timed_seconds = time.perf_counter() - timed_start
        timed_frames = live._stats()[0] - first_count
        assert live.presented > 3, repr(
            dict(
                raw_swaps=raw_swaps,
                pending=live.pending_present,
                visible=live.preview_visible,
                source=desktop.main_window.findChild(QObject, "captureImage")
                .property("source")
                .toString(),
                initialized=desktop.main_window.isSceneGraphInitialized(),
            )
        )
        live.showOutput(0, True)
        pump(0.5)
        assert not live.output_excluded and live.output_window.isVisible()
        assert live.output_window.visibility() == QWindow.FullScreen
        QTest.keyClick(live.output_window, Qt.Key_Escape)
        pump(0.2)
        assert live.output_window.visibility() != QWindow.FullScreen
        assert live.output_window.grabWindow().save(
            str(args.output / "output-window.png")
        )
        # Hidden windows/pages must not keep requesting images; showing either
        # must resume the latest frame without restarting capture.
        main_image = desktop.main_window.findChild(QObject, "captureImage")
        desktop.main_window.hide()
        pump(0.2)
        assert main_image.property("source").toString() == ""
        submitted, requests = live.submitted, live.provider.requests
        wait(lambda: live.submitted >= submitted + 10)
        assert live.provider.requests - requests == live.submitted - submitted
        live.output_window.hide()
        pump(0.1)
        submitted, requests = live.submitted, live.provider.requests
        pump(0.3)
        assert live.submitted == submitted and live.provider.requests == requests
        live.showOutput(0, False)
        wait(lambda: live.submitted > submitted + 2)
        desktop.main_window.showNormal()
        pump(0.2)
        assert main_image.property("source").toString() != ""
        desktop.main_window.setProperty("page", 2)
        pump(0.2)
        assert main_image.property("source").toString() == ""
        desktop.main_window.setProperty("page", 0)
        pump(0.2)
        assert main_image.property("source").toString() != ""
        live.setPreviewVisible(False)
        count = live.submitted
        wait(lambda: live.submitted > count + 2, 10)
        assert live.output_presented > 2, "output must actually swap frames"
        live.output_window.hide()
        live.setPreviewVisible(True)
        oracle.resize(400, 280)
        wait(lambda: live.provider.image.width() == 1200, 15)
        assert live._stats()[2] > 1
        assert desktop.main_window.grabWindow().save(str(args.output / "gui.png"))
        report = live.report()
        report.update(
            test_source=args.source,
            path_rate_locked_while_active=True,
            hidden_image_requests_paused=True,
            both_hidden_gui_copy_paused=True,
            window_and_page_restore=True,
            timed_input_width=width,
            timed_input_height=height,
            timed_seconds=timed_seconds,
            processed_fps=timed_frames / timed_seconds,
            main_visible=desktop.main_window.isVisible(),
            main_exposed=desktop.main_window.isExposed(),
            eye_channel_differences=difference,
            processed_in_five_seconds=timed_frames,
            output_exclusion=True,
            fullscreen_escape=True,
            resize=True,
        )
        live.showOutput(0, False)
        pump(0.1)
        live.stop()
        assert live.provider.image.isNull() and desktop.lease.owner == "live"
        pump(0.1)
        blank = live.output_window.grabWindow().convertToFormat(QImage.Format_RGB888)
        blank_rgb = np.frombuffer(blank.bits(), np.uint8).reshape(
            blank.height(), blank.bytesPerLine()
        )[:, : blank.width() * 3]
        assert np.mean(blank_rgb) < 10, "stop must remove old pixels from actual output"
        report["output_cleared_on_stop"] = True
        live.output_window.hide()
        wait(lambda: not live.active, 15)
        assert desktop.lease.owner is None
        live.start()
        wait(lambda: live.submitted >= 2)
        oracle.showMinimized()
        wait(lambda: not live.active, 15)
        assert live.provider.image.isNull() and desktop.lease.owner is None
        report["restart_source_loss_cleanup"] = True
        oracle.showNormal()
        pump(0.2)
        live.start()
        wait(lambda: live.submitted >= 2)
        live.process.terminate()  # crash only the test's own session worker
        wait(lambda: not live.active, 15)
        assert live.provider.image.isNull() and desktop.lease.owner is None
        report["worker_crash_cleanup"] = True
        (args.output / "report.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    key: value
                    for key, value in report.items()
                    if not key.endswith("_ms")
                },
                ensure_ascii=True,
            )
        )
    finally:
        live.stop()
        end = time.perf_counter() + 15
        while live.active and time.perf_counter() < end:
            pump(0.05)
        oracle.close()
        if oracle.video is not None:
            oracle.video.release()
        shiboken6.delete(engine)


if __name__ == "__main__":
    main()
