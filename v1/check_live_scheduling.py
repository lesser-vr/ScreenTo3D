"""Real host/native scheduling with a slower owned source and pause/resume."""
import argparse
import json
from pathlib import Path
import time

import shiboken6
from PySide6.QtCore import QEventLoop, QTimer, Qt
from screento3d_app.desktop import create_app
from screento3d_app.presentation_policy import PresentationCadence, NativeDeliveryCadence
from live_benchmark_source import SourceProcess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    app, qml, desktop = create_app()
    live = desktop.live
    live.output_placement.path = args.output / 'placement.json'
    source = None
    errors, sessions = [], []
    live.errorOccurred.connect(errors.append)

    def pump(seconds):
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        timer.setTimerType(Qt.PreciseTimer)
        timer.timeout.connect(loop.quit)
        timer.start(max(1, round(seconds * 1000)))
        loop.exec()

    def wait(predicate):
        deadline = time.monotonic() + 90
        while not predicate():
            pump(.02)
            if errors:
                raise RuntimeError(errors[-1])
            if time.monotonic() > deadline:
                raise TimeoutError(live.status)

    def count():
        return live.native.report()['output']['submitted_frames'] if live.nativeEnabled else live.output_presented

    try:
        source = SourceProcess('FloorballGame', interval_ms=40)
        source.resize(round(960 / source.devicePixelRatioF()), round(540 / source.devicePixelRatioF()))
        source.request('activate')
        pump(.2)
        live.items = [dict(kind='window', id=int(source.winId()), pid=source.pid,
                           label='Owned cadence regression', width=960, height=540)]
        live.select(0)
        live.setMode('performance')
        for path, hz in (('gpu', 60), ('gpu-texture', 60), ('gpu-texture', 30)):
            live.setProcessingPath(path)
            live.setPresentationHz(hz)
            live.startMinimal()
            wait(lambda: count() >= 5)
            assert type(live.cadence) is (NativeDeliveryCadence if live.nativeEnabled else PresentationCadence)
            assert bool(live.native_wakeup) == live.nativeEnabled
            before = count()
            pump(2)
            moving = count() - before
            assert moving >= 10 and not errors
            source.request('pause')
            pump(.3)
            polls = live.poll_count
            pump(1)
            idle_polls = live.poll_count - polls
            assert live.active and not errors
            if live.nativeEnabled:
                assert idle_polls < 200
            source.request('resume')
            before = count()
            wait(lambda: count() >= before + 5)
            live.stop()
            wait(lambda: not live.active)
            assert live.native_wakeup is None and not live.delivery_timer.isActive()
            if live.native is not None:
                assert live.native.report()['live_nodes'] == live.native.report()['live_pools'] == 0
            sessions.append(dict(path=path, hz=hz, moving_frames=moving, paused_polls=idle_polls,
                                 resumed=True, notification_closed=True, cleanup_zero=True))
        report = dict(success=True, source_interval_ms=40, sessions=sessions, errors=errors)
        (args.output / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report), flush=True)
    finally:
        if live.active:
            live.stop()
            wait(lambda: not live.active)
        if source is not None:
            source.close()
        shiboken6.delete(qml)


if __name__ == '__main__':
    main()
