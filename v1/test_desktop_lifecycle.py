"""Real GUI-worker cancellation/error/retry gates with prior-output sentinels."""

import argparse
import json
import time
from pathlib import Path
from unittest.mock import patch

import shiboken6
from screento3d_app.desktop import create_app
from PySide6.QtWidgets import QMessageBox

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT / "out/public-live-default/FloorballGame.mp4",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    app, engine, controller = create_app()
    window = engine.rootObjects()[0]
    window.setProperty("page", 1)
    controller.add_paths([str(args.input)])
    evidence = []
    sentinel = b"ScreenTo3D test prior output; must survive failure/cancellation"

    def wait_until(predicate, timeout=90):
        deadline = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() > deadline:
                raise TimeoutError(controller.status)
            app.processEvents()
            time.sleep(0.01)

    def start_with_prior(name):
        target = args.output / (name + ".mp4")
        target.write_bytes(sentinel)
        controller.rows[0]["output"] = str(target)
        controller.changed.emit()
        with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            controller.start()
        assert controller.busy, controller.status
        return target

    for name in ("immediate-cancel", "processing-cancel", "close-cancel"):
        target = start_with_prior(name)
        if name != "immediate-cancel":
            wait_until(lambda: controller.progress > 0 or not controller.busy)
            assert controller.busy, "Fixture ended before cancellation"
        if name == "close-cancel":
            exits = []
            controller.exitReady.disconnect(app.quit)
            controller.exitReady.connect(lambda exits=exits: exits.append(True))
            with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
                assert not controller.requestClose()
        else:
            controller.cancel()
        wait_until(lambda: not controller.busy)
        assert controller.rows[0]["state"] == "cancelled", controller.status
        assert target.read_bytes() == sentinel
        assert controller.temp is None and controller.process is None
        if name == "close-cancel":
            assert exits == [True]
            controller.closing = False
        evidence.append({"case": name, "preserved": True, "cleaned": True})

    controller.setOption("mode", "video-quality")
    controller.setOption("model", "ovda-small-c16")
    controller.setOption("noncommercial", True)
    controller.setOption("engine", str(args.output))
    target = start_with_prior("invalid-engine")
    wait_until(lambda: not controller.busy)
    assert controller.rows[0]["state"] == "failed"
    assert target.read_bytes() == sentinel
    assert controller.temp is None and controller.process is None
    evidence.append(
        {"case": "invalid-engine", "preserved": True, "cleaned": True}
    )

    for mode in ("performance", "balanced", "video-quality", "offline-quality"):
        controller.setOption("mode", mode)
        target = args.output / (mode + ".mp4")
        controller.rows[0]["output"] = str(target)
        controller.start()
        assert controller.busy
        wait_until(lambda: not controller.busy)
        assert controller.canOpen and controller.rows[0]["state"] == "completed", (
            controller.status
        )
        assert controller.temp is None and controller.process is None
        evidence.append({"case": "retry-" + mode, "complete": True, "cleaned": True})

    assert not list(args.output.glob("*.partial*"))
    (args.output / "report.json").write_text(
        json.dumps(evidence, indent=2), encoding="utf-8"
    )
    print(json.dumps(evidence), flush=True)
    window.hide()
    shiboken6.delete(engine)


if __name__ == "__main__":
    main()
