"""Bounded real desktop VFG opt-in check, capturing only an owned public fixture."""
import argparse
import json
import sys
import time
from pathlib import Path

from PySide6.QtCore import QObject, QMetaObject, Qt
import shiboken6

from screento3d_app.desktop import create_app
from live_benchmark_source import SourceProcess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cap', type=int, choices=(0, 30, 60), default=0)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    app, engine, desktop = create_app()
    live = desktop.live
    live.setPresentationHz(args.cap)
    live.output_placement.path = args.output / 'placement.json'
    errors, sessions = [], []
    live.errorOccurred.connect(errors.append)
    source = None

    def pump(seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.001)

    def wait(predicate, seconds=90):
        deadline = time.monotonic() + seconds
        while not predicate():
            pump(.02)
            if errors:
                raise RuntimeError(errors[-1])
            if time.monotonic() > deadline:
                raise TimeoutError(live.status)

    def stop():
        live.stop()
        wait(lambda: not live.active, 25)
        pump(.1)
        report = live.native.report()
        assert report['live_pools'] == report['live_nodes'] == 0
        assert not live.hasFrame
        assert live.native_wakeup is None and not live.delivery_timer.isActive()
        return report

    try:
        pump(.2)
        assert live.vfgEnabled is False and live.native is None
        assert 'torch' not in sys.modules and 'screento3d_app.vfg_renderer' not in sys.modules
        desktop.main_window.setProperty('page', 3)
        pump(.3)
        toggle = desktop.main_window.findChild(QObject, 'vfgEnabled')
        assert toggle is not None and toggle.property('visible') and not toggle.property('checked')
        tools = desktop.main_window.findChild(QObject, 'toolsWindow')
        tools.grabWindow().save(str(args.output / 'options-default.png'))
        # Exercise the QML button's click handler, not just its Python setter.
        assert QMetaObject.invokeMethod(toggle, 'toggle', Qt.DirectConnection)
        assert QMetaObject.invokeMethod(toggle, 'clicked', Qt.DirectConnection)
        assert live.vfgEnabled
        live.setMode('video-quality')
        pump(.05)
        assert live.vfgUnavailableReason and live.vfgEnabled
        assert toggle.property('enabled')  # A checked unsupported option can still be turned off.
        live.setVfg(False)
        pump(.05)
        assert not toggle.property('enabled')
        live.setMode('balanced')
        desktop.main_window.setProperty('page', 0)
        source = SourceProcess('FloorballGame', interval_ms=16)
        source.resize(round(1920 / source.devicePixelRatioF()), round(1080 / source.devicePixelRatioF()))
        source.request('activate')
        pump(.3)
        live.items = [dict(kind='window', id=int(source.winId()), pid=source.pid,
                           label='Owned VFG option test', width=1920, height=1080)]
        live.select(0)
        live.setVfg(True)
        live.setProcessingPath('gpu')
        live.startMinimal()
        assert not live.active and errors and 'VFG' in errors[-1]
        assert desktop.error_dialog.isVisible()
        desktop.error_dialog.close()
        errors.clear()
        live.setProcessingPath('gpu-texture')
        for mode, enabled in [('balanced', False), ('balanced', True),
                              ('balanced', False), ('performance', True), ('performance', False)]:
            live.setMode(mode)
            live.setVfg(enabled)
            assert live.vfgEnabled is enabled
            live.startMinimal()
            wait(lambda: live.native is not None and live.native.report()['output']['submitted_frames'] >= 8)
            # This case validates each fixed configuration; running transitions
            # are covered by test_sbs_start.py --vfg-switch with actual hotkeys.
            pump(1.5)
            assert not errors
            if enabled:
                assert getattr(live.native, 'vfg_delivery', False)
                assert any(row[4] == 1 for row in live.native.records.values())
                live.output_window.hide()
                pump(.2)
                live.output_window.showNormal()
                before = live.native.report()['output']['submitted_frames']
                wait(lambda: live.native.report()['output']['submitted_frames'] > before + 4)
                if mode == 'performance':
                    for width, height in ((3840, 2160), (1920, 1080)):
                        generation = live.native.pool.generation
                        source.resize(round(width / source.devicePixelRatioF()), round(height / source.devicePixelRatioF()))
                        source.request('activate')
                        wait(lambda: live.native.pool is not None and live.native.pool.generation > generation
                             and live.native.pool.width == width * 2 and live.native.pool.height == height)
                        before = live.native.report()['output']['submitted_frames']
                        wait(lambda: live.native.report()['output']['submitted_frames'] > before + 8)
            else:
                assert not getattr(live.native, 'vfg_delivery', False)
            sessions.append(dict(mode=mode, vfg=enabled, processed=live._stats()[0],
                                 submitted=live.native.report()['output']['submitted_frames']))
            stop()
        (args.output / 'result.json').write_text(json.dumps(dict(
            success=True, cap=args.cap, default_disabled=True, qml_click=True, unsupported_explained=True,
            error_dialog=True, small_4k_resize=True,
            sessions=sessions, cleanup_zero=True), indent=2))
        print(json.dumps(sessions), flush=True)
    finally:
        if live.active:
            live.stop()
            deadline = time.monotonic() + 25
            while live.active and time.monotonic() < deadline:
                pump(.02)
        if source is not None:
            source.close()
        shiboken6.delete(engine)


if __name__ == '__main__':
    main()
