"""Generated-window capture oracle; never save other desktop/window pixels."""

import argparse
import json
import os
import time
from unittest.mock import patch
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget, QMessageBox
import shiboken6

from screento3d_app.desktop import create_app


class Oracle(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ScreenTo3D generated capture oracle")
        self.setWindowFlags(
            Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setGeometry(1100, 50, 480, 320)
        self.sequence = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.advance)
        self.timer.start(16)

    def advance(self):
        self.sequence += 1
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        w, h = self.width(), self.height()
        for color, x, y in [
            ("red", 0, 0),
            ("green", w // 2, 0),
            ("blue", 0, h // 2),
            ("white", w // 2, h // 2),
        ]:
            p.fillRect(x, y, w // 2, h // 2, QColor(color))
        p.fillRect(self.sequence % (w - 30), h // 2 - 12, 30, 24, QColor("yellow"))
        p.setPen(QColor("black"))
        p.drawText(w // 2 + 10, h // 2 + 30, f"GENERATED {self.sequence}")
        timestamp_ms = time.perf_counter_ns() // 1_000_000
        for bit in range(48):
            p.fillRect(
                bit * 6,
                0,
                6,
                8,
                QColor("white" if timestamp_ms & (1 << bit) else "black"),
            )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=5)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    app, engine, desktop = create_app()
    desktop.live.setSbs(False)  # Capture-only diagnostic, not a user-facing mode.
    main_window = engine.rootObjects()[0]
    main_window.setPosition(0, 0)
    main_window.resize(980, 700)
    oracle = Oracle()
    oracle.show()
    live = desktop.live

    def pump(seconds):
        until = time.perf_counter() + seconds
        while time.perf_counter() < until:
            app.processEvents()
            time.sleep(0.005)

    def wait(predicate, seconds=15):
        until = time.perf_counter() + seconds
        while not predicate() and time.perf_counter() < until:
            pump(0.05)
        assert predicate(), live.status

    pump(0.5)
    source = dict(
        kind="window",
        id=int(oracle.winId()),
        pid=os.getpid(),
        label=oracle.windowTitle(),
        width=720,
        height=480,
    )
    live.items = [source]
    live.selected = 0
    live.changed.emit()
    live.start()
    wait(lambda: live.submitted > 3 or not live.active)
    assert live.active and live.submitted > 3, live.status
    assert desktop.busy and desktop.lease.owner == "live"
    desktop.checkSetup()
    assert desktop.lease.owner == "live"
    desktop.add_paths([str(Path("out/v1-all-modes-input.mp4").resolve())])
    desktop.start()
    assert desktop.process is None and desktop.lease.owner == "live"
    pump(args.seconds)
    image = live.provider.image
    assert not image.isNull()
    colors = [
        image.pixelColor(int(image.width() * x), int(image.height() * y)).name()
        for x, y in ((0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.8))
    ]
    assert colors == ["#ff0000", "#008000", "#0000ff", "#ffffff"], colors
    image.save(str(args.output / "generated-window.png"))
    main_window.grabWindow().save(str(args.output / "preview-gui.png"))
    report = {"window": live.report(), "colors": colors}
    original_shape = (image.width(), image.height())
    oracle.resize(400, 280)
    wait(
        lambda: (live.provider.image.width(), live.provider.image.height())
        != original_shape
    )
    assert live.meta[10] > 0
    report["resize"] = live.report()
    live.timer.setInterval(200)
    pump(2)
    assert live.meta[5] > 0
    report["overload"] = live.report()
    live.stop()
    wait(lambda: not live.active)
    assert not desktop.busy and live.provider.image.isNull()
    live.timer.setInterval(33)
    for reason in ("minimized", "closed"):
        if reason == "closed":
            oracle.showNormal()
        live.start()
        wait(lambda: live.submitted > 2 or not live.active)
        assert live.active
        if reason == "minimized":
            oracle.showMinimized()
        else:
            oracle.close()
        wait(lambda: not live.active)
        assert not desktop.busy and live.provider.image.isNull()
        report[reason] = live.status
    oracle.showNormal()
    pump(0.2)
    live.items[0]["id"] = int(oracle.winId())
    live.start()
    wait(lambda: live.submitted > 2 or not live.active)
    assert live.active
    desktop.exitReady.disconnect(app.quit)
    exits = []
    desktop.exitReady.connect(lambda: exits.append(True))
    with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
        assert not desktop.requestClose()
    wait(lambda: not live.active)
    assert exits == [True] and not desktop.busy and live.provider.image.isNull()
    report["close_gui"] = "capture joined and exclusive lease released before exitReady"
    (args.output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "window_frames": report["window"]["received"],
                "colors": colors,
                "minimized": report["minimized"],
                "closed": report["closed"],
            }
        ),
        flush=True,
    )
    oracle.close()
    main_window.hide()
    shiboken6.delete(engine)


if __name__ == "__main__":
    main()
