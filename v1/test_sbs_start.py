"""Actual QML start -> isolated WGC -> DA2 Base -> SBS, generated pixels only."""
import argparse
import json
import multiprocessing as mp
import os
import time
from pathlib import Path


def fixture(connection):
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer
    from test_live_preview import Oracle

    app = QApplication([])
    window = Oracle()
    screen = app.primaryScreen().availableGeometry()
    window.move(screen.x() + 30, screen.y() + 30)
    window.show()
    app.processEvents()
    connection.send(dict(kind="window", id=int(window.winId()), pid=os.getpid(),
                         label="Generated SBS start fixture", width=480, height=320))
    timer = QTimer()
    timer.timeout.connect(lambda: app.quit() if connection.poll() else None)
    timer.start(100)
    app.exec()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--path", choices=("gpu", "gpu-texture"), default="gpu")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    from PySide6.QtCore import QObject, QPointF, Qt
    from PySide6.QtTest import QTest
    from depthsbs_app.desktop import create_app
    import shiboken6

    context = mp.get_context("spawn")
    connection, child_connection = context.Pipe()
    child = context.Process(target=fixture, args=(child_connection,))
    child.start()
    app, engine, desktop = create_app()
    window = engine.rootObjects()[0]
    live = desktop.live
    live.output_placement.path = args.output / "placement.json"
    live.setProcessingPath(args.path)
    results = {}

    def pump(seconds=.1):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            app.processEvents()
            time.sleep(.005)

    def wait(predicate, seconds=60):
        until = time.monotonic() + seconds
        while not predicate() and time.monotonic() < until:
            pump()
        assert predicate(), live.status

    def click(name):
        button = window.findChild(QObject, name)
        assert button.property("enabled"), name
        point = button.mapToScene(QPointF(button.width()/2, button.height()/2)).toPoint()
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point)
        pump()

    def stop():
        live.stop()
        wait(lambda: not live.active, 20)
        assert not desktop.busy

    try:
        wait(connection.poll, 15)
        source = connection.recv()
        live.items, live.selected = [source], 0
        live.changed.emit()
        pump()
        click("captureStart")
        def count():
            return live.native.report()['output']['submitted_frames'] if live.nativeEnabled else live.output_presented
        wait(lambda: count() >= 3 or not live.active)
        assert live.active and not live.stopping and count() >= 3, live.status
        assert live.output_window.isVisible()
        assert live.output_excluded
        assert not live.preview_visible
        assert window.findChild(QObject, 'captureStart').property('text') == 'SBS 중지'
        assert live.output_window.grabWindow().save(str(args.output/'sbs.png'))
        assert window.grabWindow().save(str(args.output/'controller.png'))
        # Moving and resizing the real output is preserved across stop/restart.
        live.output_window.resize(640, 400)
        live.output_window.setPosition(140, 140)
        pump(.4)
        normal = live.output_window.geometry()
        QTest.keyClick(live.output_window, Qt.Key_F11)
        pump(.3)
        from PySide6.QtGui import QWindow
        assert live.output_window.visibility() == QWindow.FullScreen
        QTest.keyClick(live.output_window, Qt.Key_Escape)
        pump(.3)
        assert live.output_window.visibility() == QWindow.Windowed
        live.output_window.showMinimized(); pump(.3)
        assert live.active and not live.stopping
        live.output_window.showNormal(); pump(.3)
        import ctypes as C
        from ctypes import wintypes as W
        from depthsbs_app.capture_sources import user32
        user32.GetWindowDisplayAffinity.argtypes = [W.HWND, C.POINTER(W.DWORD)]
        affinity = W.DWORD()
        assert user32.GetWindowDisplayAffinity(int(live.output_window.winId()), C.byref(affinity))
        assert affinity.value == 0x11
        results["output"] = dict(frames=count(), status=live.status,
                                 capture_affinity=affinity.value, path=args.path)
        live.output_window.close()
        pump()
        assert not live.hasFrame and not live.output_window.isVisible()
        wait(lambda: not live.active, 20)
        assert not desktop.busy
        click('captureStart')
        wait(lambda: count() >= 3 or not live.active)
        assert live.active and count() >= 3
        assert live.output_window.geometry() == normal, (live.output_window.geometry(), normal)
        click('captureStart')
        wait(lambda: not live.active, 20)
        assert not live.output_window.isVisible() and not desktop.busy
        # Cancellation while the first frame is being prepared releases the lease.
        click('captureStart')
        assert live.active
        click('captureStart')
        wait(lambda: not live.active, 20)
        assert not desktop.busy and not live.hasFrame
        results['checks'] = ['actual QML start', 'actual Base inference', 'sole output consumer',
                             'F11/Esc', 'minimize keeps running', 'X stops', 'restart placement',
                             'button stop', 'preparation cancel']
        results["passed"] = True
    except Exception as error:
        results["error"] = str(error)
        raise
    finally:
        if live.active:
            stop()
        connection.send("stop")
        child.join(5)
        if child.is_alive():
            child.terminate()
            child.join(5)
        (args.output / "report.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        shiboken6.delete(engine)


if __name__ == "__main__":
    main()
