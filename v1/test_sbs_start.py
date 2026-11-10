"""Actual QML start -> isolated WGC -> DA2 Base -> SBS, generated pixels only."""
import argparse
import json
import multiprocessing as mp
import os
import time
from pathlib import Path


def fixture(connection, source_size=None):
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer
    from test_live_preview import Oracle

    app = QApplication([])
    window = Oracle()
    if source_size:
        dpr=window.devicePixelRatioF()
        window.resize(round(source_size[0]/dpr),round(source_size[1]/dpr))
    screen = app.primaryScreen().availableGeometry()
    window.move(screen.x() + 30, screen.y() + 30)
    window.show()
    app.processEvents()
    import ctypes
    from ctypes import wintypes
    rect=wintypes.RECT()
    user32=ctypes.windll.user32
    user32.GetClientRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
    if not user32.GetClientRect(int(window.winId()),ctypes.byref(rect)):
        raise OSError('Cannot read fixture client geometry')
    connection.send(dict(kind="window", id=int(window.winId()), pid=os.getpid(),
                         label="Generated SBS start fixture",
                         width=rect.right-rect.left,
                         height=rect.bottom-rect.top))
    timer = QTimer()
    def command():
        if connection.poll():
            message=connection.recv()
            if message == 'activate':
                window.raise_()
                window.activateWindow()
            elif isinstance(message,tuple) and message[0]=='resize':
                dpr=window.devicePixelRatioF()
                window.resize(round(message[1]/dpr),round(message[2]/dpr))
                app.processEvents()
                resized=wintypes.RECT()
                if not user32.GetClientRect(int(window.winId()),ctypes.byref(resized)):
                    raise OSError('Cannot read resized fixture geometry')
                connection.send((resized.right-resized.left,resized.bottom-resized.top))
            else:
                app.quit()
    timer.timeout.connect(command)
    timer.start(100)
    app.exec()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--path", choices=("gpu", "gpu-texture"), default="gpu")
    parser.add_argument("--vfg", action="store_true")
    parser.add_argument("--vfg-switch", action="store_true")
    parser.add_argument("--layout", choices=("full-sbs", "half-sbs", "full-tb", "half-tb"), default="full-sbs")
    parser.add_argument("--mode", choices=("performance", "balanced", "video-quality"), default="balanced")
    parser.add_argument('--model', choices=('da2-small','da2-base','vda-small','ovda-small-c16'))
    parser.add_argument('--noncommercial', action='store_true')
    parser.add_argument('--source-size',type=int,nargs=2,metavar=('WIDTH','HEIGHT'))
    parser.add_argument('--resize-input',action='store_true')
    parser.add_argument('--require-gpu-usage',action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    from PySide6.QtCore import QObject, QPointF, Qt
    from PySide6.QtTest import QTest
    from depthsbs_app.desktop import create_app
    from depthsbs_app.desktop_preferences import DesktopPreferences
    from PySide6.QtCore import QSettings
    import shiboken6

    context = mp.get_context("spawn")
    connection, child_connection = context.Pipe()
    child = context.Process(target=fixture, args=(child_connection,args.source_size))
    child.start()
    app, engine, desktop = create_app(DesktopPreferences(QSettings(str((args.output/'preferences.ini').resolve()),QSettings.IniFormat)))
    window = engine.rootObjects()[0]
    live = desktop.live
    live.output_placement.path = args.output / "placement.json"
    live.setProcessingPath(args.path)
    live.setMode(args.mode)
    if args.model:
        live.setLiveModel(args.model)
        assert live.liveModel==args.model
        if args.model=='ovda-small-c16':
            assert args.noncommercial, 'Explicit non-commercial test scope is required'
            live.setOvdaConfirmed(True)
    live.setStereoLayout(args.layout)
    if args.vfg:
        live.setVfg(True)
        assert live.vfgEnabled
    import depthsbs_app.desktop as desktop_module
    results = dict(app_module=desktop_module.__file__, mode=args.mode, layout=args.layout)
    errors = []
    live.errorOccurred.connect(errors.append)

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
        from depthsbs_app.stereo_layout import dimensions
        assert (live.meta[2], live.meta[3]) == dimensions(source["width"], source["height"], args.layout), live.meta
        if live.nativeEnabled:
            assert (live.native.pool.width, live.native.pool.height) == (live.meta[2], live.meta[3])
        wait(lambda: " ms" in live.output_window.title())
        if args.vfg:
            import re
            wait(lambda: re.search(r"보간 [1-9]\d* fps", live.output_window.title()))
        results["title"] = live.output_window.title()
        if args.resize_input:
            results['input_resizes']=[]
            for width,height in ((1920,1080),(1080,1920),(1024,1024),(1056,608),(source['width'],source['height'])):
                before=count()
                connection.send(('resize',width,height))
                wait(connection.poll,15)
                physical=connection.recv()
                wait(lambda:tuple(live.meta[2:4])==dimensions(*physical,args.layout) and count()>=before+3,90)
                assert live.active and live.gpu_capture_selected and not errors,(live.status,errors)
                results['input_resizes'].append(dict(requested=[width,height],output=list(live.meta[2:4]),gpu_capture=True))
        if args.vfg_switch:
            from unittest.mock import patch
            from PySide6.QtGui import QWindow
            import ctypes
            assert live.nativeEnabled and not args.vfg
            assert desktop.vfg_hotkey.registered, live.vfgShortcut
            assert live.vfgShortcut.endswith('Ctrl+Alt+S')
            output = live.output_window
            output.resize(640, 400)
            output.setPosition(140, 140)
            pump(.3)
            geometry = output.geometry()
            failed_session = live.session
            # Missing/corrupt optional runtime must leave the old stream intact.
            with patch('depthsbs_app.vfg_runtime.validate_runtime', side_effect=RuntimeError('Injected missing VFG runtime')):
                live.setVfg(True)
            assert live.active and not live.stopping and not live.vfgSwitching
            assert live.session == failed_session and output.isVisible()
            assert desktop.error_dialog.isVisible()
            desktop.error_dialog.close()
            errors.clear()
            switch_results = []
            notice = window.findChild(QObject, 'vfgNotice')
            def global_toggle():
                # Request the owned input; Windows may retain another app's focus.
                # RegisterHotKey must work in either case, outside this Qt process.
                user32 = ctypes.windll.user32
                user32.GetForegroundWindow.restype = ctypes.c_void_p
                user32.AllowSetForegroundWindow(source['pid'])
                connection.send('activate')
                pump(.2)
                if user32.GetForegroundWindow() != source['id']:
                    foreground = user32.GetForegroundWindow()
                    user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
                    foreground_thread = user32.GetWindowThreadProcessId(foreground, None)
                    current_thread = ctypes.windll.kernel32.GetCurrentThreadId()
                    attached = user32.AttachThreadInput(current_thread, foreground_thread, True)
                    try:
                        user32.SetForegroundWindow(ctypes.c_void_p(source['id']))
                    finally:
                        if attached:
                            user32.AttachThreadInput(current_thread, foreground_thread, False)
                pump(.1)
                foreground_pid = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(foreground_pid))
                if foreground_pid.value == os.getpid():
                    # A synthetic Alt press releases Windows' foreground lock.
                    user32.keybd_event(0x12, 0, 0, 0)
                    user32.keybd_event(0x12, 0, 2, 0)
                    user32.SetForegroundWindow(ctypes.c_void_p(source['id']))
                    pump(.1)
                    user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(foreground_pid))
                results['hotkey_foreground_pid'] = foreground_pid.value
                results['hotkey_test_pid'] = os.getpid()
                assert foreground_pid.value != os.getpid()
                for key in (0x11, 0x12, 0x53):
                    user32.keybd_event(key, 0, 0, 0)
                for key in (0x53, 0x12, 0x11):
                    user32.keybd_event(key, 0, 2, 0)
                wait(lambda: live.vfgSwitching or bool(errors), 3)
                assert not errors, errors

            for fullscreen, enabled in ((False, True), (False, False), (True, True), (True, False)):
                if fullscreen and output.visibility() != QWindow.FullScreen:
                    output.showFullScreen()
                    pump(.3)
                session = live.session
                switch_started = time.monotonic()
                global_toggle()
                assert output.isVisible() and live.transitionImageUrl
                assert notice.property('pending') and notice.opacity() == 1
                assert output.grabWindow().save(str(args.output / f'notice-{session}-preparing.png'))
                live.toggleVfg()  # Repeated requests ignored until completion.
                wait(lambda: not live.vfgSwitching and live.hasFrame or not live.active, 90)
                assert live.active and live.vfgEnabled == enabled, live.status
                assert live.source == source and live.session == session + 1
                assert output.isVisible() and (output.visibility() == QWindow.FullScreen) == fullscreen
                assert fullscreen or output.geometry() == geometry
                assert not live.transitionImageUrl
                assert notice.property('message') == ('VFG ON' if enabled else 'VFG OFF')
                assert not notice.property('pending') and notice.opacity() == 1
                assert output.grabWindow().save(str(args.output / f'notice-{session}-complete.png'))
                pump(1.9)
                assert notice.opacity() == 0 and notice.property('message') == ''
                wait(lambda: count() >= 8)
                assert bool(getattr(live.native, 'vfg_delivery', False)) == enabled
                if enabled:
                    wait(lambda: any(record[4] == 1 for record in live.native.records.values()))
                switch_results.append(dict(vfg=enabled, fullscreen=fullscreen, session=live.session,
                                           submitted=count(), title=output.title(),
                                           transition_seconds=round(time.monotonic() - switch_started, 3)))
            output.showNormal()
            pump(.3)
            global_toggle()
            live.stop()
            wait(lambda: not live.active, 25)
            assert not live.vfgSwitching and not desktop.busy and not output.isVisible()
            assert not live.transitionImageUrl
            assert notice.opacity() == 0
            pump(.5)
            assert not live.active  # No deferred restart after cancellation.
            assert live.native.report()['live_pools'] == live.native.report()['live_nodes'] == 0
            live.startMinimal()
            wait(lambda: count() >= 3 or not live.active)
            assert live.active and live.hasFrame and output.isVisible()
            results['vfg_switch'] = dict(sessions=switch_results, global_hotkey=True,
                                         preflight_preserves_output=True, cancel_no_restart=True)
        before_switch = count()
        click("openFiles")
        assert window.property("page") == 1 and not window.findChild(QObject, "convertButton").property("enabled")
        wait(lambda: count() >= before_switch + 3)
        click("returnLive")
        assert window.property("page") == 0 and live.active
        assert not live.output_excluded
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
        overlay = window.findChild(QObject, "fullscreenStatsOverlay")
        toggle = window.findChild(QObject, "fullscreenStatsToggle")
        initial = toggle.property("checked")
        try:
            for enabled in (False, True):
                if toggle.property("checked") != enabled:
                    toggle.click()
                pump()
                assert overlay.property("visible") == enabled
            assert live.output_window.grabWindow().save(str(args.output/'fullscreen-stats.png'))
            labels = []
            pending = list(overlay.childItems())
            while pending:
                item = pending.pop()
                if item.objectName() == "stereoStatsLabel":
                    labels.append(item)
                pending.extend(item.childItems())
            assert len(labels) == 2
            if args.require_gpu_usage:
                import re
                wait(lambda:re.search(r'GPU (?:100|[1-9]?\d)%',live.output_window.title()) is not None,10)
            assert 'GPU ' in live.output_window.title()
            for label in labels:
                assert 'GPU ' in label.property('text')
                assert label.property('text') in live.output_window.title()
            results['gpu_debug_display']=dict(title=live.output_window.title(),
                                             overlays=[label.property('text') for label in labels])
            for label in labels:
                start = label.mapToScene(QPointF(0, 0))
                end = label.mapToScene(QPointF(8, 8))
                expected_x = 16 if args.layout == "half-tb" else 8
                expected_y = 16 if args.layout == "half-sbs" else 8
                assert abs(end.x() - start.x() - expected_x) < .01
                assert abs(end.y() - start.y() - expected_y) < .01
                if args.layout.startswith("half"):
                    # The receiver expands the packed Half axis by two.
                    decoded_x = expected_x * (2 if args.layout == "half-sbs" else 1)
                    decoded_y = expected_y * (2 if args.layout == "half-tb" else 1)
                    assert decoded_x == decoded_y == 16
                assert label.property("font").pixelSize() == 8
        finally:
            if toggle.property("checked") != initial:
                toggle.click()
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
        assert affinity.value == 0
        assert live.output_window.transientParent() is None
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
        results['screens'] = []
        for screen in app.screens():
            output = live.output_window
            output.showNormal()
            output.setScreen(screen)
            output.setPosition(screen.availableGeometry().topLeft())
            output.showFullScreen()
            before = count()
            wait(lambda: output.screen() == screen and count() >= before + 3)
            assert user32.GetWindowDisplayAffinity(int(output.winId()), C.byref(affinity))
            assert affinity.value == 0
            results['screens'].append(screen.name())
        output.showNormal()
        click('captureStart')
        wait(lambda: not live.active, 20)
        assert not live.output_window.isVisible() and not desktop.busy
        # Cancellation while the first frame is being prepared releases the lease.
        click('captureStart')
        assert live.active
        click('captureStart')
        wait(lambda: not live.active, 20)
        assert not desktop.busy and not live.hasFrame
        for kind, expected in [('monitor', 0x11), ('window', 0)]:
            live.setKind(kind)
            assert live.configureOutputCapture(live.output_window)
            assert user32.GetWindowDisplayAffinity(int(live.output_window.winId()), C.byref(affinity))
            assert affinity.value == expected
        results['checks'] = ['actual QML start', f'actual {live.liveModel} inference', 'sole output consumer',
                             'F11/Esc', 'minimize keeps running', 'X stops', 'restart placement',
                             'button stop', 'preparation cancel']
        results["passed"] = True
    except Exception as error:
        results["error"] = str(error)
        results["reported_errors"] = errors
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
