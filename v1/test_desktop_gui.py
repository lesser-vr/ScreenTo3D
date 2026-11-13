"""Real Qt/D3D11 smoke, screenshots and optional isolated conversion evidence."""

import argparse
import json
import time
from pathlib import Path

from screento3d_app.desktop import create_app
from screento3d_app.desktop_preferences import DesktopPreferences
from PySide6.QtCore import QObject, QPointF, Qt, QSettings
from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
from PySide6.QtTest import QTest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--model", default="da2-small")
    parser.add_argument("--codec", default="h264")
    parser.add_argument("--cancel", action="store_true")
    parser.add_argument("--error", action="store_true")
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    app, engine, controller = create_app(DesktopPreferences(QSettings(str(args.output/'preferences.ini'), QSettings.IniFormat)))
    warnings = []
    engine.warnings.connect(
        lambda errors: warnings.extend(e.toString() for e in errors)
    )
    window = engine.rootObjects()[0]
    pattern = window.findChild(QQuickWindow, "patternWindow")
    tools = window.findChild(QQuickWindow, "toolsWindow")

    def pump(seconds):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            app.processEvents()
            time.sleep(0.01)

    pump(1)
    assert window.findChild(QObject, "modePicker").property("currentText") == "DA2 Small · FP16 · 기본"
    graphics = str(window.rendererInterface().graphicsApi())
    assert (
        window.rendererInterface().graphicsApi() == QSGRendererInterface.Direct3D11
    ), graphics
    window.grabWindow().save(str(args.output / "live.png"))
    window.setProperty("page", 1)
    if args.input:
        controller.add_paths([str(args.input)])
        controller.setOption("mode", {"da2-small": "performance", "da2-base": "balanced"}.get(args.model, "video-quality"))
        controller.setOption("model", args.model)
        controller.setOption("codec", args.codec)
        controller.setOption("noncommercial", args.model == "ovda-small-c16")
        target = args.output / "converted.mp4"
        if target.exists():
            raise ValueError("Use a fresh output directory")
        controller.rows[0]["output"] = str(target)
        if args.error:
            controller.setOption("engine", str(args.output))
        controller.changed.emit()
    pump(0.5)
    window.grabWindow().save(str(args.output / "files.png"))
    controller.setOption("mode", "offline-quality")
    window.setProperty("page", 2)
    pump(0.2)
    assert (
        window.findChild(QObject, "modePicker").property("currentText").startswith("VDA Small · 5프레임 · FP")
    )
    tools.grabWindow().save(str(args.output / "settings-offline.png"))
    controller.setOption("mode", "balanced")
    controller.checkSetup()
    until = time.monotonic() + 45
    while controller.busy and time.monotonic() < until:
        pump(0.1)
    assert not controller.busy, "Setup timed out"
    pump(0.2)
    tools.grabWindow().save(str(args.output / "settings.png"))
    pattern.show()
    pump(0.5)
    assert pattern.rendererInterface().graphicsApi() == QSGRendererInterface.Direct3D11
    pattern.grabWindow().save(str(args.output / "output-window.png"))
    pattern.showFullScreen()
    pump(0.5)
    assert pattern.visibility() == QQuickWindow.FullScreen
    pattern.grabWindow().save(str(args.output / "output-fullscreen.png"))
    pattern.showNormal()
    pump(0.2)
    pattern.hide()
    window.resize(380, 260)
    pump(0.3)
    window.grabWindow().save(str(args.output / "minimum-size.png"))
    window.resize(420, 260)
    window.setProperty("page", 1)
    if args.input:
        pump(0.2)
        button = window.findChild(QObject, "convertButton")
        point = button.mapToScene(
            QPointF(button.width() / 2, button.height() / 2)
        ).toPoint()
        QTest.mouseClick(tools, Qt.LeftButton, Qt.NoModifier, point)
        pump(0.1)
        assert controller.busy, controller.status
        if args.cancel:
            controller.cancel()
        until = time.monotonic() + 300
        while controller.busy and time.monotonic() < until:
            pump(0.1)
        assert not controller.busy, "Worker timed out"
        expected = "cancelled" if args.cancel else "failed" if args.error else "completed"
        assert controller.rows[0]["state"] == expected, controller.status
        assert controller.canOpen == (expected == "completed")
        assert controller.temp is None and controller.lease.owner is None
        pump(0.2)
        window.grabWindow().save(str(args.output / "result.png"))
    assert not warnings, warnings
    report = {
        "graphics": graphics,
        "warnings": warnings,
        "setup": controller.setup,
        "status": controller.status,
        "jobs": controller.rows,
        "fullscreen": True,
        "scope": "Qt D3D11 generated scene, not CUDA texture import or live capture",
    }
    (args.output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False), flush=True)
    window.hide()
    import shiboken6

    shiboken6.delete(engine)
    assert not warnings, warnings
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
