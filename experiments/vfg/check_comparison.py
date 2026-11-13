"""Bounded real-GUI launcher smoke using only an owned public video window."""
import argparse
import ctypes as ct
from ctypes import wintypes as wt
import json
from pathlib import Path
import subprocess
import sys
import time

from PySide6.QtCore import QMetaObject, QPoint, Qt
from PySide6.QtGui import QGuiApplication
import shiboken6

from compare_desktop import create_comparison
from live_benchmark_source import SourceProcess
from screento3d_app.capture_sources import is_sbs_output, user32
from screento3d_app.live_sbs import DEFAULT_STEREO_QUALITY


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vfg", action="store_true")
    parser.add_argument("--model", choices=('da2-base','da2-small'), default='da2-base')
    parser.add_argument("--owned-output-control", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    app, engine, desktop, observer = create_comparison(args.output.resolve(), args.vfg, args.model)
    live = desktop.live
    if args.owned_output_control:
        # Negative control only: reproduce the pre-fix native owner relationship.
        live.output_window.setTransientParent(desktop.main_window)
    # Do not alter the user's remembered A/B output placement during smoke.
    live.output_placement.path = args.output / "placement.json"
    errors = []
    live.errorOccurred.connect(errors.append)
    source = None
    checks = {}

    def pump(seconds):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            app.processEvents()
            time.sleep(.001)

    def wait(predicate, timeout=90):
        until = time.monotonic() + timeout
        while not predicate():
            pump(.02)
            if errors:
                raise RuntimeError(errors[-1])
            if time.monotonic() > until:
                raise TimeoutError(live.status)

    def affinity(window):
        value = wt.DWORD()
        user32.GetWindowDisplayAffinity.argtypes = [wt.HWND, ct.POINTER(wt.DWORD)]
        assert user32.GetWindowDisplayAffinity(int(window.winId()), ct.byref(value))
        return value.value

    try:
        pump(.2)
        assert not live.active and live.selected == -1 and live.native is None
        assert observer.label in desktop.main_window.title()
        assert live.live_model == args.model and live.strength == .5
        assert live.presentationHz == 60
        live.setStrength(1.)
        assert QMetaObject.invokeMethod(live, 'resetStrength', Qt.DirectConnection)
        assert live.strength == .5
        checks['selected_model_half_strength_reset_and_60fps_default'] = True
        checks["no_automatic_capture_or_native_load"] = True
        # Invoke the Qt slot, exercising the subclass's pre-capture guard.
        live.setMode("balanced" if args.model == 'da2-small' else 'performance')
        assert QMetaObject.invokeMethod(live, "start", Qt.DirectConnection)
        assert errors and ('DA2 Small' if args.model == 'da2-small' else 'DA2 Base') in errors[-1] and not live.active
        assert desktop.error_dialog.isVisible() and affinity(desktop.error_dialog) == 0x11
        desktop.error_dialog.close()
        errors.clear()
        live.setMode('performance' if args.model == 'da2-small' else 'balanced')
        checks["unsupported_model_rejected_before_capture"] = True
        source = SourceProcess("FloorballGame", interval_ms=0)
        source.resize(round(1920/source.devicePixelRatioF()), round(1080/source.devicePixelRatioF()))
        pump(.3)
        live.items = [dict(kind="window", id=int(source.winId()), pid=source.pid,
                           label="Owned public comparison test", width=1920, height=1080)]
        live.select(0)
        assert QMetaObject.invokeMethod(live, "startMinimal", Qt.DirectConnection)
        wait(lambda: len(observer.rows) >= 2)
        assert not errors and all(row["output_fps"] > 0 for row in observer.rows)
        assert any(row["generated_fps"] > 0 for row in observer.rows) == args.vfg
        assert "fps" in desktop.main_window.title()
        checks["start_button_path_and_live_counts"] = True
        assert affinity(live.output_window) == 0 and not live.output_excluded
        assert affinity(desktop.main_window) == 0x11
        assert is_sbs_output(live.output_window.winId())
        child_code = '''
import sys
from screento3d_app.capture_sources import is_sbs_output, validate_source, windows
hwnd = int(sys.argv[1])
assert is_sbs_output(hwnd)
assert all(row['id'] != hwnd for row in windows())
try:
    validate_source(dict(kind='window', id=hwnd, pid=0))
except ValueError as error:
    assert 'SBS 출력 창' in str(error)
else:
    raise AssertionError('Recursive output capture was accepted')
'''
        subprocess.run([sys.executable, "-c", child_code, str(int(live.output_window.winId()))],
                       check=True, timeout=15, capture_output=True)
        checks["output_capturable_controls_protected_cross_process_recapture_rejected"] = True
        for screen in QGuiApplication.screens():
            live.output_window.setPosition(screen.availableGeometry().topLeft() + QPoint(40, 40))
            before = live.native.report()["output"]["submitted_frames"]
            wait(lambda: live.native.report()["output"]["submitted_frames"] > before + 5)
            assert affinity(live.output_window) == 0 and live.output_window.isVisible()
        checks["output_moves_across_connected_screens"] = len(QGuiApplication.screens())
        # A transient QML output resolves GA_ROOTOWNER to the small control
        # window. External full-screen discovery needs an independent root.
        user32.GetWindow.argtypes = [wt.HWND, wt.UINT]
        user32.GetWindow.restype = wt.HWND
        user32.GetAncestor.argtypes = [wt.HWND, wt.UINT]
        user32.GetAncestor.restype = wt.HWND
        hwnd = int(live.output_window.winId())
        expected_owner = int(desktop.main_window.winId()) if args.owned_output_control else None
        assert user32.GetWindow(hwnd, 4) == expected_owner  # GW_OWNER
        assert user32.GetAncestor(hwnd, 3) == (expected_owner or hwnd)  # GA_ROOTOWNER
        live.output_window.showFullScreen()
        live.output_window.requestActivate()
        pump(6)
        assert live.output_window.isVisible() and affinity(live.output_window) == 0
        rect = wt.RECT()
        assert user32.GetWindowRect(hwnd, ct.byref(rect))
        checks["fullscreen_output"] = dict(independent=not args.owned_output_control,
                                            hwnd=hwnd, rect=[rect.left, rect.top, rect.right, rect.bottom])
        live.output_window.showNormal()
        live.output_window.hide()
        pump(.2)
        live.output_window.showNormal()
        before = live.native.report()["output"]["submitted_frames"]
        wait(lambda: live.native.report()["output"]["submitted_frames"] > before + 5)
        assert affinity(live.output_window) == 0
        checks["capture_policy_survives_hide_restore"] = True
        live.stop()
        wait(lambda: not live.active)
        pump(.3)
        first = json.loads((args.output / "session-1.json").read_text(encoding="utf-8"))
        assert first["state"] == "stopped" and first["cleanup"] == dict(live_pools=0, live_nodes=0, has_frame=False)
        assert first['stereo_quality'] == DEFAULT_STEREO_QUALITY == 'detail'
        assert "Owned public comparison test" not in json.dumps(first)
        checks["stop_cleanup_and_identity_free_report"] = True
        # Start again and close via the ordinary window-close owner path.
        assert QMetaObject.invokeMethod(live, "startMinimal", Qt.DirectConnection)
        wait(lambda: live.hasFrame)
        assert desktop.requestClose() is False
        wait(lambda: not live.active)
        observer.finish()
        second = json.loads((args.output / "session-2.json").read_text(encoding="utf-8"))
        assert second["cleanup"] == dict(live_pools=0, live_nodes=0, has_frame=False)
        checks["restart_and_close_cleanup"] = True
        (args.output / "smoke.json").write_text(json.dumps(dict(completed=True, vfg=args.vfg, model=args.model, checks=checks), indent=2))
        print(json.dumps(checks), flush=True)
    finally:
        if live.active:
            live.stop()
            until = time.monotonic() + 25
            while live.active and time.monotonic() < until:
                pump(.02)
        observer.timer.stop()
        observer.finish()
        if source is not None:
            source.close()
        shiboken6.delete(engine)


if __name__ == "__main__":
    main()
