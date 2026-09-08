"""Cursor inclusion test on generated pixels, restores original pointer position."""

import argparse
import json
import os
import time
from pathlib import Path
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QCursor
import shiboken6
from depthsbs_app.desktop import create_app
from test_live_preview import Oracle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    app, engine, desktop = create_app()
    window = engine.rootObjects()[0]
    oracle = Oracle()
    oracle.setCursor(Qt.CrossCursor)
    oracle.show()
    oracle.timer.stop()
    original = QCursor.pos()
    live = desktop.live

    def pump(seconds):
        deadline = time.perf_counter() + seconds
        while time.perf_counter() < deadline:
            app.processEvents()
            time.sleep(0.005)

    def wait(predicate):
        deadline = time.perf_counter() + 15
        while not predicate() and time.perf_counter() < deadline:
            pump(0.05)
        assert predicate(), live.status

    try:
        pump(0.3)
        live.items = [
            dict(
                kind="window",
                id=int(oracle.winId()),
                pid=os.getpid(),
                label="Generated cursor test",
                width=720,
                height=480,
            )
        ]
        live.selected = 0
        QCursor.setPos(oracle.mapToGlobal(QPoint(80, 80)))
        pump(0.3)
        images = []
        for enabled in (False, True):
            live.setCursor(enabled)
            live.start()
            wait(lambda: live.submitted > 0 or not live.active)
            assert live.active
            pump(0.5)
            scale = oracle.devicePixelRatioF()
            image = live.provider.image.copy(
                int(60 * scale), int(60 * scale), int(40 * scale), int(40 * scale)
            )
            image.save(str(args.output / f"generated-cursor-{enabled}.png"))
            images.append(image)
            live.stop()
            wait(lambda: not live.active)
        changed = sum(
            images[0].pixel(x, y) != images[1].pixel(x, y)
            for y in range(images[0].height())
            for x in range(images[0].width())
        )
        assert changed > 0, "Cursor toggle did not change generated cursor region"
        (args.output / "report.json").write_text(
            json.dumps(dict(cursor_changed_pixels=changed, stopped=True)),
            encoding="utf-8",
        )
        print("Cursor changed pixels:", changed)
    finally:
        QCursor.setPos(original)
        if live.active:
            live.stop()
            wait(lambda: not live.active)
        oracle.close()
        window.hide()
        shiboken6.delete(engine)


if __name__ == "__main__":
    main()
