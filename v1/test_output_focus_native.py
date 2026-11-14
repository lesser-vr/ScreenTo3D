"""Owned-window Win32/Qt/D3D11 focus regression; no user-app input is injected."""
import argparse
import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import time

from PySide6.QtCore import QMetaObject, QObject, QSettings, Qt
from PySide6.QtGui import QWindow
from screento3d_app.desktop import create_app
from screento3d_app.desktop_preferences import DesktopPreferences
from screento3d_app.output_focus import NOACTIVATE, TOPMOST
import shiboken6


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--background', action='store_true', help='Verify no focus theft without requesting foreground activation')
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    from test_live_preview import Oracle
    app, engine, c = create_app(DesktopPreferences(QSettings(str(args.output/'preferences.ini'), QSettings.IniFormat)))
    live = c.live; live.output_placement.path = args.output/'placement.json'
    oracle = Oracle(); oracle.setGeometry(20, 40, 426, 240); oracle.show()
    c.main_window.setPosition(550, 40)
    window = live.output_window; policy = live.output_policy; api = policy.api
    hwnd, source = int(window.winId()), int(oracle.winId())
    report = dict(passed=False, background_only=args.background, cases=[], scope='Owned generated source and actual Qt/D3D11 output; not physical mouse/game/Owl3D acceptance or an FPS benchmark')
    def pump(seconds=.15):
        deadline = time.monotonic()+seconds
        while time.monotonic()<deadline:
            app.processEvents(); time.sleep(.003)
    def wait(predicate, seconds=40):
        deadline=time.monotonic()+seconds
        while not predicate() and time.monotonic()<deadline: pump(.03)
        assert predicate(), str(live.status)
    def check(name, **details):
        report['cases'].append(dict(name=name, **details)); print(name, flush=True)
    def activate(target):
        assert api.activate((target, os.getpid())), str(dict(error='Windows rejected owned-fixture foreground activation', target=target, identity=api.identity(target), pid=os.getpid(), visible=bool(api.user.IsWindowVisible(target)), iconic=bool(api.user.IsIconic(target)), foreground=api.foreground()))
        pump(); assert api.foreground()==target
    def send(code, lparam=0, wparam=0):
        api.user.SendMessageW.argtypes=[W.HWND, W.UINT, W.WPARAM, W.LPARAM]
        api.user.SendMessageW.restype=C.c_ssize_t
        return api.user.SendMessageW(hwnd, code, wparam, lparam)
    try:
        pump(.4); c.syncRuntimes()
        live.items=[dict(kind='window', id=source, pid=os.getpid(), label='Owned generated focus source', width=426, height=240)]
        live.selected=0; live.setMode('performance'); live.setStereoLayout('half-tb')
        live.setPresentationHz(60); live.setProcessingPath('gpu-texture')
        expected = api.foreground() if args.background else source
        if not args.background: activate(int(c.main_window.winId()))
        live.startSbs(0, 0); window.setGeometry(20, 420, 500, 280)
        assert live.active, str(live.status)
        wait(lambda:live.hasFrame and not policy.focus.pending or not live.active)
        assert live.active, str(live.status)
        pump()
        assert api.foreground()==expected
        print(dict(policy_hwnd=policy.hwnd, current_hwnd=int(window.winId()), style=hex(api.user.GetWindowLongPtrW(int(window.winId()),-20)), managing=policy.focus.managing, reasons=sorted(policy.reasons)),flush=True)
        assert api.user.GetWindowLongPtrW(hwnd, -20)&NOACTIVATE
        assert api.user.GetWindowLongPtrW(hwnd, -20)&TOPMOST
        check('first_frame_no_focus_theft_noactivate_topmost' if args.background else 'first_frame_source_focus_noactivate_topmost')
        assert send(0x21, (0x201<<16)|1, hwnd)==3
        assert api.foreground()==expected
        check('client_click_noactivate_mouse_message_not_eaten')
        for iteration in range(3):
            live.toggleOutputFullscreen(); pump(.4)
            assert window.visibility()==QWindow.FullScreen
            assert api.foreground()==expected
            assert api.user.GetWindowLongPtrW(hwnd, -20)&NOACTIVATE
            live.toggleOutputFullscreen(); pump(.4)
            assert window.visibility()==QWindow.Windowed
            assert api.foreground()==expected
        check('three_fullscreen_restore_cycles_preserve_focus_and_hwnd', hwnd_stable=int(window.winId())==hwnd)
        assert int(window.winId())==hwnd
        assert send(0x21, (0x201<<16)|2, hwnd)==1
        if not args.background: activate(hwnd)
        send(0x231); window.resize(540, 304); send(0x232); pump()
        assert api.foreground()==expected and not policy.focus.managing
        check('native_frame_resize_management_no_focus_theft' if args.background else 'native_frame_resize_management_returns_focus')
        menu = c.main_window.findChild(QObject, 'outputMenu')
        assert menu is not None
        assert QMetaObject.invokeMethod(menu, 'popup')
        pump(); assert menu.property('visible') and policy.focus.managing
        if not args.background: activate(hwnd)
        assert QMetaObject.invokeMethod(menu, 'close')
        pump(); assert not menu.property('visible') and not policy.focus.managing
        assert api.foreground()==expected
        check('actual_qml_context_menu_no_focus_theft' if args.background else 'actual_qml_context_menu_returns_source_focus')
        assert policy.registered
        assert len(policy.hooks)==2
        check('foreground_and_window_lifecycle_hooks_registered')
        C.windll.user32.PostThreadMessageW(C.windll.kernel32.GetCurrentThreadId(),0x312,policy.identifier,0)
        pump(.4)
        assert window.visibility()==QWindow.FullScreen and api.foreground()==expected
        live.toggleOutputFullscreen(); pump(.3)
        check('registered_global_hotkey_dispatch_preserves_focus')
        wait(lambda:live.native.report()['output']['submitted_frames']>=15)
        report['native']=live.native.report()
        live.stop(); wait(lambda:not live.active,15); pump(.2)
        assert not policy.registered and not policy.focus.pending
        counts=live.native.report()
        assert counts['live_pools']==counts['live_nodes']==0
        check('stop_releases_hotkey_and_graphics_resources')
        report['passed']=True
    finally:
        live.stop(); wait(lambda:not live.active,15)
        oracle.close(); c.main_window.close(); app.processEvents(); shiboken6.delete(engine)
        (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':main()
