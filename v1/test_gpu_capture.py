"""Actual synthetic-window WGC -> CUDA color, resize, owner and closure checks."""
import os
import time
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import torch
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget
from screento3d_app.gpu_capture import GpuCapture


def main():
    os.environ['QT_SCALE_FACTOR'] = '1'
    os.environ['QT_ENABLE_HIGHDPI_SCALING'] = '0'
    app = QApplication([])
    window = QWidget(None, Qt.FramelessWindowHint)
    window.setStyleSheet('background-color: rgb(31, 79, 173);')
    window.resize(640, 360)
    window.show()
    app.processEvents()
    source = dict(kind='window', id=int(window.winId()), pid=os.getpid(), width=640, height=360)
    stream = torch.cuda.Stream()
    for cycle in range(10):
        with GpuCapture(source, False, 0) as capture:
            for width, height in ((640, 360), (803, 451), (320, 640)):
                window.resize(width, height)
                deadline = time.monotonic() + 5
                observed = []
                while time.monotonic() < deadline:
                    app.processEvents()
                    result = capture.read(stream)
                    if result is not None:
                        observed.append(result[1])
                    ratio = window.devicePixelRatioF()
                    if result is not None and result[0].shape[:2] == (round(height*ratio), round(width*ratio)):
                        image, meta = result
                        pixels = image.cpu().numpy()  # Explicit test-only readback.
                        # A ContentSize change can precede the fixture's paint.
                        # Wait for the settled, uniformly repainted source.
                        if not np.all(pixels[20:-20,20:-20,:3] == [173,79,31]):
                            continue
                        now = time.perf_counter_ns()
                        # WGC uses the compositor's presentation timestamp,
                        # which may be a few milliseconds after callback time.
                        assert 0 < meta['callback_ns'] <= now
                        assert abs(meta['source_ns'] - meta['callback_ns']) < 100_000_000, (meta, now)
                        assert now - meta['source_ns'] < 5e9
                        print(dict(cycle=cycle, size=[width,height], metadata=meta), flush=True)
                        break
                    time.sleep(.005)
                else:
                    raise AssertionError(('No correctly resized GPU frame', cycle, width, height, window.width(), window.height(), observed[-5:]))
            with ThreadPoolExecutor(1) as pool:
                try:
                    pool.submit(capture.read, stream).result()
                except RuntimeError:
                    pass
                else:
                    raise AssertionError('Foreign thread accepted')
            if cycle == 9:
                window.hide()
                app.processEvents()
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    try:
                        capture.read(stream)
                    except (ValueError, RuntimeError):
                        break
                    time.sleep(.02)
                else:
                    raise AssertionError('Hidden active source did not stop')
    window.hide()
    app.processEvents()
    try:
        GpuCapture(source, False, 0)
    except ValueError:
        pass
    else:
        raise AssertionError('Hidden source accepted')
    window.close()
    print('PASS: thirty GPU captures, resize, restart, owner, active and initial hidden-source rejection', flush=True)


if __name__ == '__main__':
    main()
