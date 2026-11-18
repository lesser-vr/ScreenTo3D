"""Qt bridge for playback focus, explicit window management and fullscreen hotkey."""
import ctypes as C
from ctypes import wintypes as W
import sys

from PySide6.QtCore import QAbstractNativeEventFilter, QTimer
from PySide6.QtGui import QWindow

from .shortcut_keys import FULLSCREEN
from .messages import Message as M
from .output_focus import FocusSession, NOACTIVATE, Win32Windows


class StyleChange(C.Structure):
    _fields_ = [('old', W.DWORD), ('new', W.DWORD)]


class OutputWindowPolicy(QAbstractNativeEventFilter):
    shortcut = FULLSCREEN.keys
    identifier = FULLSCREEN.identifier

    def __init__(self, app, live, main, *, api=None):
        super().__init__()
        self.app, self.live, self.window = app, live, live.output_window
        self.api = api or (Win32Windows() if sys.platform == 'win32' else None)
        self.hwnd = int(self.window.winId())
        self.focus = FocusSession(self.api, main=int(main.winId()), output=self.hwnd) if self.api else None
        self.reasons = set()
        self.move_geometry = None
        self.registered = self.closed = False
        self.state = None
        self.hooks, self.event_callback = [], None
        self.order_timer = QTimer(live)
        self.order_timer.setSingleShot(True)
        self.order_timer.timeout.connect(self.reorder)
        self.finish_timer = QTimer(live)
        self.finish_timer.setSingleShot(True)
        self.finish_timer.timeout.connect(self.finish_click)
        self.transition_timer = QTimer(live)
        self.transition_timer.setSingleShot(True)
        self.transition_timer.timeout.connect(self.finish_transition)
        if self.api:
            self.api.noactivate(self.hwnd, True)
            app.installNativeEventFilter(self)
        self.window.visibleChanged.connect(self.sync)
        live.changed.connect(self.sync)
        live.frameChanged.connect(self.first_frame)
        app.aboutToQuit.connect(self.close)
        live.output_shortcut = M('Toggle fullscreen · {v0}', v0=self.shortcut)

    def arm(self, source):
        if self.focus:
            self.focus.arm(source)

    def first_frame(self):
        if self.focus and self.focus.pending and self.live.hasFrame and self.window.isVisible():
            self.focus.ready()
            self.queue_order()

    def sync(self, *_):
        if self.closed or not self.api:
            return
        shown = bool((self.live.active or self.live.vfgSwitching) and self.window.isVisible())
        if shown == self.state:
            return
        self.state = shown
        if shown:
            self.refresh_handle()
            self.hooks, self.event_callback = self.api.watch_windows(self.queue_order)
            self.registered = bool(self.api.user.RegisterHotKey(None, self.identifier, FULLSCREEN.modifiers, FULLSCREEN.key))
            self.live.output_shortcut = (M('Toggle fullscreen · {v0}', v0=self.shortcut) if self.registered else
                M('Cannot register {v0} · Check whether another app uses this shortcut.', v0=self.shortcut))
            self.live.changed.emit()
            self.queue_order()
        else:
            self.api.unwatch_windows(self.hooks)
            self.hooks, self.event_callback = [], None
            self.cancel()
            self.api.place(self.hwnd, -2)
            if self.registered:
                self.api.user.UnregisterHotKey(None, self.identifier)
                self.registered = False

    def refresh_handle(self):
        hwnd = int(self.window.winId())
        if hwnd != self.hwnd:
            self.hwnd = self.focus.output = hwnd
            self.api.noactivate(hwnd, not self.focus.managing)

    def queue_order(self):
        if not self.closed and self.state and not self.order_timer.isActive():
            self.order_timer.start(0)

    def reorder(self):
        if not self.closed and self.state and not self.focus.managing:
            self.refresh_handle()
            self.api.order(self.hwnd)

    def begin(self, reason='menu', previous=None):
        if self.closed or not self.state:
            return
        if self.focus:
            self.focus.begin(previous)
            self.reasons.add(reason)
            self.api.noactivate(self.hwnd, False)

    def end(self, reason='menu'):
        self.reasons.discard(reason)
        if reason == 'menu':
            self.reasons.difference_update(('click', 'caption'))
        if not self.reasons and self.focus and self.focus.managing:
            self.api.noactivate(self.hwnd, True)
            self.focus.finish()
            self.queue_order()

    def finish_click(self):
        self.end('click')

    def finish_transition(self):
        self.end('caption')
        self.end('click')

    def stop_session(self):
        if self.focus:
            self.focus.finish()
        self.cancel()

    def cancel(self):
        self.finish_timer.stop()
        self.transition_timer.stop()
        self.move_geometry = None
        self.order_timer.stop()
        self.reasons.clear()
        if self.focus:
            self.focus.cancel()
            self.api.noactivate(self.hwnd, True)

    def toggle_fullscreen(self):
        if not self.live.active or self.live.stoppingNow or not self.window.isVisible():
            return
        diagnostics = getattr(self.live, 'diagnostics', None)
        if diagnostics is not None:diagnostics.note('fullscreen_requested', was_fullscreen=self.window.visibility()==QWindow.FullScreen)
        self.live.rememberOutput()
        if self.window.visibility() == QWindow.FullScreen:
            self.window.showNormal()
        else:
            self.window.showFullScreen()
        # Let Qt finish the visibility/style change before returning input.
        # A still-open context menu holds its own management reason.
        self.transition_timer.start(0)
        self.queue_order()

    def nativeEventFilter(self, event_type, message):
        if self.closed or not self.api or bytes(event_type) not in (b'windows_generic_MSG', b'windows_dispatcher_MSG'):
            return False, 0
        msg = W.MSG.from_address(int(message))
        code, hwnd = msg.message, int(msg.hWnd or 0)
        if code == 0x0312 and self.registered and msg.wParam == self.identifier:
            QTimer.singleShot(0, self.toggle_fullscreen)
            return True, 0
        if hwnd != self.hwnd:
            if self.state and code in (0x0006, 0x001C):  # Controls/dialog activation.
                self.queue_order()
            return False, 0
        if code == 0x007C and C.c_int(msg.wParam & 0xffffffff).value == -20 and msg.lParam:
            style = StyleChange.from_address(msg.lParam)
            style.new = style.new & ~NOACTIVATE if self.focus.managing else style.new | NOACTIVATE
        if not self.state:
            return False, 0
        if code == 0x0021:  # WM_MOUSEACTIVATE: permit frame/context menu only.
            hit, mouse = msg.lParam & 0xffff, (msg.lParam >> 16) & 0xffff
            if hit != 1 or mouse in (0x0204, 0x00A4):
                self.begin('caption' if hit == 2 else 'click')
                return True, 1  # MA_ACTIVATE, mouse message is preserved.
            return True, 3  # MA_NOACTIVATE, not MA_NOACTIVATEANDEAT.
        if code == 0x0231:
            self.move_geometry = self.window.geometry()
            self.begin('move')
        elif code == 0x0232:
            if self.move_geometry is not None and self.window.geometry() != self.move_geometry:
                self.reasons.discard('caption')
            self.move_geometry = None
            self.reasons.discard('move')
            self.finish_timer.start(0)
        elif code == 0x0211:
            self.begin('menu')
        elif code == 0x0212:
            self.end('menu')
        elif code in (0x00A2, 0x0202):
            self.finish_timer.start(0)
        elif code == 0x0112:
            if msg.wParam & 0xfff0 in (0xf020, 0xf030, 0xf060, 0xf120):
                self.reasons.discard('caption')
            self.finish_timer.start(0)
        elif code == 0x0006:  # Explicit taskbar/Alt+Tab activation is management.
            if msg.wParam & 0xffff and self.api.foreground() == self.hwnd:
                self.begin('click', int(msg.lParam or 0))
            elif not msg.wParam & 0xffff and not self.api.belongs(int(msg.lParam or 0), self.hwnd):
                self.reasons.clear()
                self.api.noactivate(self.hwnd, True)
                self.focus.managing = False
                self.focus.target = None
                self.queue_order()
        elif code in (0x0003, 0x0005):  # Move/resize, never per-frame repaint.
            self.queue_order()
        return False, 0

    def close(self, *_):
        if self.closed:
            return
        self.cancel()
        if self.api:
            self.api.unwatch_windows(self.hooks)
            self.hooks, self.event_callback = [], None
            if self.registered:
                self.api.user.UnregisterHotKey(None, self.identifier)
            self.app.removeNativeEventFilter(self)
        self.registered = False
        self.closed = True
