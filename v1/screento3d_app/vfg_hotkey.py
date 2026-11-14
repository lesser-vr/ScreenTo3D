"""Application-owned Windows global hotkey; never intercept another app's key."""

from .shortcut_keys import VFG
from .messages import Message as M

import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter


class VfgHotkey(QAbstractNativeEventFilter):
    shortcut = VFG.keys
    identifier = VFG.identifier
    modifiers = VFG.modifiers
    key = VFG.key

    def __init__(self, app, live):
        super().__init__()
        self.app = app
        self.live = live
        self.registered = False
        self.user32 = None
        if not live.vfgConfigurable:
            return
        if sys.platform == "win32":
            self.user32 = ctypes.WinDLL("user32", use_last_error=True)
            self.user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
            self.user32.RegisterHotKey.restype = wintypes.BOOL
            self.user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
            self.user32.UnregisterHotKey.restype = wintypes.BOOL
            self.registered = bool(self.user32.RegisterHotKey(None, self.identifier, self.modifiers, self.key))
        if self.registered:
            app.installNativeEventFilter(self)
            app.aboutToQuit.connect(self.close)
            live.vfg_shortcut = M('Toggle VFG · {v0}', v0=self.shortcut)
        else:
            live.vfg_shortcut = M('Cannot register {v0} · Check whether another app uses this shortcut.', v0=self.shortcut)
        live.changed.emit()

    def nativeEventFilter(self, event_type, message):
        if self.registered and bytes(event_type) in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312 and msg.wParam == self.identifier:
                self.live.toggleVfg()
                return True, 0
        return False, 0

    def close(self, *_):
        if self.registered:
            self.user32.UnregisterHotKey(None, self.identifier)
            self.app.removeNativeEventFilter(self)
            self.registered = False
