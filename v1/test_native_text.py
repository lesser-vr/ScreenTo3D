"""Compare Qt text with a texture consumer against a text-only reference window."""

import argparse
import json
import multiprocessing as mp
import os
from pathlib import Path
import time

import numpy as np
from screento3d_app.texture_mailbox import TextureMailbox
from test_native_dual_window import producer

QML = b"""
import QtQuick
import QtQuick.Window
import ScreenTo3D.Native 1.0
Window {
    id: root; visible: true; width: 640; height: 400; color: "#10141c"; x: 0; y: 100
    property string sample: "ScreenTo3D"
    property int frameRevision: 0
    component Banner: Item {
        property string words: ""
        Text { x: 18; y: 15; text: parent.words; color: "#f3f4fa"; font.family: "Malgun Gothic"; font.pixelSize: 23 }
        Text { x: 18; y: 65; text: "GPU native - " + parent.words; color: "#aab3c6"; font.family: "Arial"; font.pixelSize: 18 }
        Text { x: 18; y: 115; text: "0123456789 ABCDEFGH " + parent.words; color: "#9c91ff"; font.family: "Malgun Gothic"; font.pixelSize: 17 }
    }
    Banner { width: parent.width; height: 175; words: root.sample }
    NativeSurface { x: 0; y: 180; width: parent.width; height: 220; consumer: 0; session: 1; enabledFrame: true; revision: root.frameRevision }
    Window {
        objectName: "reference"; visible: true; width: 640; height: 400; x: 660; y: 100; color: "#10141c"
        Banner { width: parent.width; height: 175; words: root.sample }
    }
}
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--old-sync", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    os.environ.setdefault("QT_D3D_NO_VBLANK_THREAD", "1")
    from PySide6.QtCore import QObject, QUrl
    from PySide6.QtGui import QGuiApplication, QImage
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
    import screento3d_app.native_delivery as native

    if args.old_sync:
        previous = (
            native.ROOT
            / "out/qt-native-delivery/pre-render-boundary/qt_native_delivery.dll"
        )

        class PreviousRoot:
            def __truediv__(self, suffix):
                assert suffix == "out/qt-native-delivery/qt_native_delivery.dll"
                return previous

        native.ROOT = PreviousRoot()
        native.NATIVE_SHA256 = (
            "367b274357e4202645860398ab1f7d34a669264e02229994513ef74a39c99b75"
        )
    QQuickWindow.setGraphicsApi(QSGRendererInterface.Direct3D11)
    app = QGuiApplication([])
    delivery = native.NativeDelivery()
    delivery.begin(1)
    engine = QQmlApplicationEngine()
    engine.loadData(QML, QUrl("native-text-test.qml"))
    assert engine.rootObjects()
    root = engine.rootObjects()[0]
    reference = root.findChild(QObject, "reference")
    for window in (root, reference):
        window.setPersistentGraphics(False)
        window.setPersistentSceneGraph(False)
    context = mp.get_context("spawn")
    box = TextureMailbox.create(context)
    parent, child = context.Pipe()
    process = context.Process(target=producer, args=(box, child))
    process.start()
    child.close()
    revision = 0

    def pump(seconds=0.05):
        nonlocal revision
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if delivery.consume(box, process.pid):
                revision += 1
                root.setProperty("frameRevision", revision)
            app.processEvents()
            delivery.check()
            time.sleep(0.002)

    def command(value):
        parent.send(value)
        deadline = time.monotonic() + 10
        while not parent.poll() and time.monotonic() < deadline:
            pump()
        assert parent.poll() and parent.recv() == "done"
        pump()

    def pixels(image):
        return (
            np.frombuffer(image.bits(), np.uint8)
            .reshape(image.height(), image.bytesPerLine())
            .copy()
        )

    rows = []
    try:
        command(("resize", 768, 192))
        for index in range(30):
            root.setProperty(
                "sample", f"한국어 출력 복원 {index:02d} - Scene {index * 13}"
            )
            if index % 5 == 0:
                root.hide()
                reference.hide()
                pump()
                root.show()
                reference.show()
            command(("paint", index % 2, index + 1, False))
            actual = root.grabWindow().convertToFormat(QImage.Format_RGBA8888)
            expected = reference.grabWindow().convertToFormat(QImage.Format_RGBA8888)
            assert actual.size() == expected.size()
            height = round(175 * root.devicePixelRatio())
            different = int(
                np.count_nonzero(pixels(actual)[:height] != pixels(expected)[:height])
            )
            rows.append(dict(iteration=index, different_channels=different))
            if different or index == 29:
                actual.save(str(args.output / f"actual-{index}.png"))
                expected.save(str(args.output / f"reference-{index}.png"))
        report = dict(
            passed=all(row["different_channels"] == 0 for row in rows),
            cases=rows,
            dll_sha256=native.NATIVE_SHA256,
            scope="Exact static UI-region comparison with text-only Qt window; 30 changes, six hide/restores",
        )
        (args.output / "report.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        print(json.dumps(report))
        assert report["passed"], "Native graphics commands changed unrelated Qt text"
    finally:
        delivery.end()
        parent.send(("stop",))
        process.join(5)
        if process.is_alive():
            process.terminate()
            process.join(5)
        process.close()
        parent.close()
        root.hide()
        reference.hide()


if __name__ == "__main__":
    main()
