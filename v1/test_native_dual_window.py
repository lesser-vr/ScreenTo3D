"""Owned synthetic two-window integration gate; not a throughput benchmark."""

import argparse
import json
import multiprocessing as mp
import os
from pathlib import Path
import sys
import time

from depthsbs_app.texture_mailbox import (
    TextureMailbox,
    TextureFrame,
    INSTALLED,
    RETIRED,
)


def producer(box, pipe):
    from depthsbs_app.live_texture_pool import LiveTexturePool

    pool = None
    generation = 0
    try:
        while True:
            if not pipe.poll(15):
                raise RuntimeError("Synthetic parent stopped responding")
            command = pipe.recv()
            if command[0] == "stop":
                break
            if command[0] == "resize":
                if pool:
                    box.retire(1, generation)
                    deadline = time.monotonic() + 5
                    while box.state() != RETIRED:
                        if time.monotonic() > deadline:
                            raise TimeoutError("Synthetic retirement timeout")
                        time.sleep(0.001)
                    pool.close()
                generation += 1
                pool = LiveTexturePool(command[1] // 2, command[2])
                box.offer(
                    pool.descriptor(1, generation), session=1, owned_pid=os.getpid()
                )
                deadline = time.monotonic() + 5
                while box.state() != INSTALLED:
                    if time.monotonic() > deadline:
                        raise TimeoutError("Synthetic installation timeout")
                    time.sleep(0.001)
            elif command[0] == "paint":
                _, slot, sequence, clear = command
                deadline = time.monotonic() + 5
                while slot not in box.writable_slots(1, generation):
                    if time.monotonic() > deadline:
                        raise TimeoutError("Synthetic slot timeout")
                    time.sleep(0.001)
                pool.check(
                    pool.dll.live_pool_paint(pool.handle, slot, sequence, int(clear))
                )
                box.publish(TextureFrame(1, generation, slot, sequence, 0, 0))
            else:
                raise ValueError("Invalid synthetic command")
            pipe.send("done")
    finally:
        if pool:
            pool.close()
        pipe.close()


QML = b"""
import QtQuick
import QtQuick.Window
import DepthSBS.Native 1.0
Window {
    id: main; objectName: "main"; visible: true; width: 512; height: 128; color: "black"
    title: "DepthSBS native generated-pattern test"
    property int frameRevision: 0
    property bool demand: true
    NativeSurface { anchors.fill: parent; consumer: 0; session: 1; enabledFrame: main.demand; revision: main.frameRevision }
    Window {
        objectName: "output"; visible: true; width: 512; height: 128; x: 540; y: 100; color: "black"
        title: "DepthSBS native generated-pattern output"
        NativeSurface { anchors.fill: parent; consumer: 1; session: 1; enabledFrame: main.demand; revision: main.frameRevision }
    }
}
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lease-error", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    os.environ.setdefault("QT_D3D_NO_VBLANK_THREAD", "1")
    from PySide6.QtCore import QObject, QUrl
    from PySide6.QtGui import QGuiApplication, QImage
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
    from depthsbs_app.native_delivery import NativeDelivery

    QQuickWindow.setGraphicsApi(QSGRendererInterface.Direct3D11)
    app = QGuiApplication([])
    delivery = NativeDelivery()
    delivery.begin(1)
    engine = QQmlApplicationEngine()
    engine.loadData(QML, QUrl("native-dual-test.qml"))
    assert engine.rootObjects(), "Native QML load failed"
    root = engine.rootObjects()[0]
    output = root.findChild(QObject, "output")
    context = mp.get_context("spawn")
    box = TextureMailbox.create(context)
    parent, child = context.Pipe()
    process = context.Process(target=producer, args=(box, child))
    process.start()
    child.close()
    revision = 0
    captures = []
    scale = root.devicePixelRatio()
    assert output.devicePixelRatio() == scale
    initial_size = (round(512 * scale), round(128 * scale))
    resized_size = (round(320 * scale), round(96 * scale))

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
        pump(0.15)

    def capture(window, label, sequence, width, height, black=False):
        image = window.grabWindow().convertToFormat(QImage.Format_RGBA8888)
        assert image.width() == width and image.height() == height, (
            image.width(),
            image.height(),
            width,
            height,
            window.devicePixelRatio(),
        )
        pixels = memoryview(image.constBits())
        count = 0
        for y in range(height):
            for x in range(width):
                i = y * image.bytesPerLine() + x * 4
                expected = (
                    (0, 0, 0, 255)
                    if black
                    else (
                        (x + sequence) % 256,
                        (y + sequence * 3) % 256,
                        (x + y + sequence * 7) % 256,
                        255,
                    )
                )
                assert tuple(pixels[i : i + 4]) == expected, (
                    label,
                    x,
                    y,
                    tuple(pixels[i : i + 4]),
                    expected,
                )
                count += 1
        assert image.save(str(args.output / f"{label}.png"))
        captures.append(
            dict(label=label, exact_pixels=count, sequence=sequence, black=black)
        )

    try:
        command(("resize", *initial_size))
        for sequence in range(1, 5):
            command(("paint", (sequence - 1) % 2, sequence, False))
        capture(root, "main", 4, *initial_size)
        capture(output, "output", 4, *initial_size)
        if args.lease_error:
            assert delivery.dll.native_publish(1, 1, 1, 5) == 0
            assert b"still leased" in delivery.dll.native_error()
            root.setProperty("demand", False)
            delivery.end()
            parent.send(("stop",))
            process.join(5)
            assert process.exitcode == 0
            for _ in range(30):
                app.processEvents()
                time.sleep(0.005)
            assert delivery.report()["live_pools"] == 0
            report = dict(
                passed=True,
                leased_slot_rejected=True,
                native=delivery.report(),
                scope="Native ABI rejects leased slot publication",
            )
            (args.output / "report.json").write_text(
                json.dumps(report, indent=2), encoding="utf-8"
            )
            print(json.dumps(report))
            return
        before = delivery.report()
        assert before["main"]["last_submitted_id"] == 4
        assert before["output"]["last_submitted_id"] == 4
        output.hide()
        for sequence in range(5, 9):
            command(("paint", (sequence - 1) % 2, sequence, False))
        hidden = delivery.report()
        assert (
            hidden["output"]["submitted_frames"] == before["output"]["submitted_frames"]
        )
        assert hidden["main"]["last_submitted_id"] == 8
        root.hide()
        for sequence in range(9, 13):
            command(("paint", (sequence - 1) % 2, sequence, False))
        both_hidden = delivery.report()
        assert (
            both_hidden["main"]["submitted_frames"]
            == hidden["main"]["submitted_frames"]
        )
        root.show()
        output.show()
        pump(0.2)
        capture(root, "main-restored", 12, *initial_size)
        capture(output, "output-restored", 12, *initial_size)
        command(("resize", *resized_size))
        root.resize(320, 96)
        output.resize(320, 96)
        command(("paint", 0, 13, False))
        capture(root, "main-resized", 13, *resized_size)
        capture(output, "output-resized", 13, *resized_size)
        command(("paint", 1, 14, True))
        capture(root, "clear", 14, *resized_size, True)
        command(("paint", 0, 15, False))
        pump(0.1)
        final_metrics = delivery.report()
        assert final_metrics["main"]["last_submitted_id"] == 15
        assert final_metrics["output"]["last_submitted_id"] == 15
        # Repainting one immutable frame is not another submitted frame ID.
        root.update()
        output.update()
        pump(0.1)
        assert (
            delivery.report()["main"]["submitted_frames"]
            == final_metrics["main"]["submitted_frames"]
        )
        root.setProperty("demand", False)
        delivery.end()
        app.processEvents()
        for _ in range(30):
            app.processEvents()
            time.sleep(0.005)
        capture(root, "stopped", 15, *resized_size, True)
        parent.send(("stop",))
        process.join(5)
        assert process.exitcode == 0
        root.hide()
        output.hide()
        root.releaseResources()
        output.releaseResources()
        for _ in range(20):
            app.processEvents()
            time.sleep(0.005)
        cleanup = delivery.report()
        assert cleanup["live_nodes"] == cleanup["live_pools"] == 0, cleanup
        assert not any(
            name == "cuda" or name.startswith("cuda.") for name in sys.modules
        )
        report = dict(
            passed=True,
            captures=captures,
            final_metrics=final_metrics,
            cleanup=cleanup,
            scope="Synthetic dual-window exact pixels and IDs; no FPS claim",
        )
        (args.output / "report.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        print(json.dumps(report))
    finally:
        delivery.end()
        root.hide()
        output.hide()
        if process.is_alive():
            process.terminate()
            process.join(5)
        process.close()
        parent.close()


if __name__ == "__main__":
    main()
