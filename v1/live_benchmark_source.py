"""Owned, request/reply-only public source for benchmark process isolation."""

import multiprocessing as mp
import os
import time


def source_main(connection, source, interval_ms=16):
    # Import Qt only in the spawned process; never share GUI objects across IPC.
    from PySide6.QtCore import QTimer, Qt
    from PySide6.QtWidgets import QApplication
    from benchmark_live_modes import ClockOracle

    app = QApplication([])
    oracle = ClockOracle(source)
    if interval_ms != 16:
        oracle.timer.setTimerType(Qt.PreciseTimer)
        oracle.timer.setInterval(interval_ms)
    oracle.show()
    redraw = QTimer()
    redraw.setTimerType(Qt.PreciseTimer)
    redraw.setInterval(max(1,interval_ms))
    redraw.timeout.connect(oracle.update)
    saved_repeat = None

    def snapshot():
        return dict(
            pid=os.getpid(),
            hwnd=int(oracle.winId()),
            dpi=oracle.devicePixelRatioF(),
            width=oracle.width(),
            height=oracle.height(),
            sequence=oracle.sequence,
            paint_count=oracle.paint_count,
            video_frames=oracle.video_frames,
            stamps=list(oracle.stamps),
            observed_ns=time.perf_counter_ns(),
            cpu_seconds=time.process_time(),
            source_interval_ms=interval_ms,
        )

    def service():
        nonlocal saved_repeat
        parent = mp.parent_process()
        if parent is not None and not parent.is_alive():
            app.quit()
            return
        try:
            if not connection.poll():
                return
            operation, payload = connection.recv()
            if operation == "resize":
                oracle.resize(*payload)
            elif operation == "activate":
                oracle.setWindowFlag(Qt.WindowStaysOnTopHint, True)
                oracle.showNormal()
                oracle.raise_()
                oracle.activateWindow()
            elif operation == "pause":
                redraw.stop()
                oracle.timer.stop()
            elif operation in ("repeat","restore_repeat"):
                oracle.timer.stop()
                if operation == "restore_repeat" and saved_repeat is not None:
                    oracle.frozen_image = saved_repeat.copy()
                elif oracle.frozen_image is None:
                    oracle.frozen_image = oracle.grab().toImage()
                if saved_repeat is None:
                    saved_repeat = oracle.frozen_image.copy()
                redraw.start()
            elif operation == "change_pixel":
                image = oracle.frozen_image
                x, y = image.width()//3, image.height()//3
                image.setPixel(x,y,image.pixel(x,y)^0xffffff)
                oracle.repaint()
            elif operation == "resume":
                redraw.stop()
                oracle.frozen_image = None
                oracle.timer.start()
            elif operation == "stop":
                connection.send({"stopped": True})
                app.quit()
                return
            elif operation != "snapshot":
                raise ValueError("Unknown source command")
            connection.send(snapshot())
        except (EOFError, BrokenPipeError, OSError, ValueError):
            app.quit()

    timer = QTimer()
    timer.timeout.connect(service)
    timer.start(5)
    try:
        connection.send(snapshot())
        app.exec()
    finally:
        oracle.close()
        if oracle.video is not None:
            oracle.video.release()
        connection.close()


class SourceProcess:
    """One outstanding command, bounded 4096-stamp replies, no frame transport."""

    def __init__(self, source, timeout=10, *, interval_ms=16):
        if type(interval_ms) is not int or not 0 <= interval_ms <= 1000:
            raise ValueError('Invalid benchmark source interval')
        context = mp.get_context("spawn")
        self.connection, child = context.Pipe()
        self.process = context.Process(target=source_main, args=(child, source, interval_ms))
        self.timeout = timeout
        if timeout <= 0:
            self.connection.close()
            child.close()
            raise ValueError("Source timeout must be positive")
        self.closed = False
        self.process.start()
        child.close()
        try:
            self.state = self._receive()
            if self.state["pid"] != self.process.pid or self.state["hwnd"] <= 0:
                raise RuntimeError("Invalid owned source identity")
        except BaseException:
            self.close()
            raise

    def _receive(self):
        if not self.connection.poll(self.timeout):
            raise TimeoutError("Owned source response timed out")
        try:
            return self.connection.recv()
        except EOFError as exc:
            raise RuntimeError("Owned source exited") from exc

    def check(self):
        if not self.process.is_alive():
            raise RuntimeError(f"Owned source exited: {self.process.exitcode}")

    def request(self, operation, payload=None):
        self.check()
        self.connection.send((operation, payload))
        self.state = self._receive()
        return self.state

    def refresh(self):
        return self.request("snapshot")

    def resize(self, width, height):
        if type(width) is not int or type(height) is not int or min(width, height) <= 0:
            raise ValueError("Source dimensions must be positive integers")
        self.request("resize", (width, height))

    def devicePixelRatioF(self):
        return self.state["dpi"]

    def winId(self):
        return self.state["hwnd"]

    @property
    def pid(self):
        return self.process.pid

    def __getattr__(self, name):
        if name in ("sequence", "paint_count", "video_frames", "stamps"):
            return self.state[name]
        raise AttributeError(name)

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            if self.process.is_alive():
                try:
                    self.request("stop")
                except (OSError, RuntimeError, TimeoutError):
                    pass
                self.process.join(timeout=5)
            if self.process.is_alive():
                self.process.terminate()  # Only this owned child.
                self.process.join(timeout=5)
            if self.process.is_alive():
                self.process.kill()
                self.process.join(timeout=5)
            if self.process.is_alive():
                raise RuntimeError("Owned source failed to stop")
        finally:
            self.connection.close()
