"""Transition-only input focus policy and narrow Win32 window operations.

No input injection, foreground polling, or changes to foreign windows.
"""
import ctypes as C
from ctypes import wintypes as W
import os
from pathlib import PureWindowsPath

NOACTIVATE = 0x08000000
TOPMOST = 0x00000008


class FocusSession:
    def __init__(self, api, *, main, output):
        self.api, self.main, self.output = api, main, output
        self.source = self.target = None
        self.pending = self.managing = False

    def arm(self, source):
        self.cancel()
        if source.get('kind') == 'window':
            self.source = (int(source['id']), int(source['pid']))
        self.pending = True

    def ready(self):
        if not self.pending:
            return
        self.pending = False
        if not self.managing and self.api.foreground() in (self.main, self.output) and self.api.usable(self.source):
            self.api.activate(self.source)

    def begin(self, previous=None):
        if self.managing:
            return
        self.managing = True
        hwnd = previous or self.api.foreground()
        target = self.api.identity(hwnd)
        # A capture-card player is not necessarily the application's input target.
        self.target = target if (target and target[1] != os.getpid()
                                  and hwnd != self.main
                                  and not self.api.belongs(hwnd, self.output)
                                  and not self.api.is_renderer(hwnd)) else self.source

    def finish(self):
        if not self.managing:
            return
        self.managing = False
        target, self.target = self.target, None
        if self.api.belongs(self.api.foreground(), self.output) and self.api.usable(target):
            self.api.activate(target)

    def cancel(self):
        self.pending = self.managing = False
        self.source = self.target = None


class Win32Windows:
    def __init__(self):
        self.user = C.WinDLL('user32', use_last_error=True)
        self.kernel = C.WinDLL('kernel32', use_last_error=True)
        signatures = {
            'GetForegroundWindow': ([], W.HWND),
            'IsWindow': ([W.HWND], W.BOOL),
            'IsWindowVisible': ([W.HWND], W.BOOL),
            'IsIconic': ([W.HWND], W.BOOL),
            'GetWindowThreadProcessId': ([W.HWND, C.POINTER(W.DWORD)], W.DWORD),
            'GetWindow': ([W.HWND, W.UINT], W.HWND),
            'GetWindowRect': ([W.HWND, C.POINTER(W.RECT)], W.BOOL),
            'GetWindowLongPtrW': ([W.HWND, C.c_int], C.c_ssize_t),
            'SetWindowLongPtrW': ([W.HWND, C.c_int, C.c_ssize_t], C.c_ssize_t),
            'SetForegroundWindow': ([W.HWND], W.BOOL),
            'SetWindowPos': ([W.HWND, W.HWND, C.c_int, C.c_int, C.c_int, C.c_int, W.UINT], W.BOOL),
            'RegisterHotKey': ([W.HWND, C.c_int, W.UINT, W.UINT], W.BOOL),
            'UnregisterHotKey': ([W.HWND, C.c_int], W.BOOL),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.user, name)
            function.argtypes, function.restype = args, result
        self.kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
        self.kernel.OpenProcess.restype = W.HANDLE
        self.kernel.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)]
        self.kernel.CloseHandle.argtypes = [W.HANDLE]
        self.enum_type = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
        self.user.EnumWindows.argtypes = [self.enum_type, W.LPARAM]
        self.event_type = C.WINFUNCTYPE(None, W.HANDLE, W.DWORD, W.HWND,
                                      W.LONG, W.LONG, W.DWORD, W.DWORD)
        self.user.SetWinEventHook.argtypes = [W.DWORD, W.DWORD, W.HMODULE, self.event_type, W.DWORD, W.DWORD, W.DWORD]
        self.user.SetWinEventHook.restype = W.HANDLE
        self.user.UnhookWinEvent.argtypes = [W.HANDLE]
        self.dwm = C.WinDLL('dwmapi')
        self.dwm.DwmGetWindowAttribute.argtypes = [W.HWND, W.DWORD, C.c_void_p, W.DWORD]

    def foreground(self):
        return int(self.user.GetForegroundWindow() or 0)

    def identity(self, hwnd):
        if not hwnd or not self.user.IsWindow(hwnd):
            return None
        pid = W.DWORD()
        self.user.GetWindowThreadProcessId(hwnd, C.byref(pid))
        return (int(hwnd), pid.value) if pid.value else None

    def usable(self, target):
        if not (target and self.identity(target[0]) == target
                and self.user.IsWindowVisible(target[0]) and not self.user.IsIconic(target[0])):
            return False
        cloaked = W.DWORD()
        result = self.dwm.DwmGetWindowAttribute(target[0], 14, C.byref(cloaked), C.sizeof(cloaked))
        return result == 0 and not cloaked.value

    def belongs(self, hwnd, owner):
        for _ in range(16):
            if not hwnd:
                return False
            if hwnd == owner:
                return True
            hwnd = int(self.user.GetWindow(hwnd, 4) or 0)  # GW_OWNER
        return False

    def activate(self, target):
        return bool(self.usable(target) and self.user.SetForegroundWindow(target[0]))

    def noactivate(self, hwnd, enabled):
        old = self.user.GetWindowLongPtrW(hwnd, -20)
        new = old | NOACTIVATE if enabled else old & ~NOACTIVATE
        if new != old:
            self.user.SetWindowLongPtrW(hwnd, -20, new)

    def place(self, hwnd, after):
        # SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_NOOWNERZORDER
        return bool(self.user.SetWindowPos(hwnd, after, 0, 0, 0, 0, 0x213))

    def image_name(self, pid):
        handle = self.kernel.OpenProcess(0x1000, False, pid)
        name, size = C.create_unicode_buffer(32768), W.DWORD(32768)
        try:
            ok = handle and self.kernel.QueryFullProcessImageNameW(handle, 0, name, C.byref(size))
            return PureWindowsPath(name.value).name.lower() if ok else ''
        finally:
            if handle:
                self.kernel.CloseHandle(handle)

    def is_renderer(self, hwnd):
        identity = self.identity(hwnd)
        return bool(identity and self.image_name(identity[1]) == 'display-mirror.exe')

    def watch_windows(self, changed):
        # Notifications are delivered on this GUI thread. Never inspect windows
        # at frame cadence, inject a DLL, or subscribe to pixel/content events.
        @self.event_type
        def event(_hook, code, hwnd, object_id, child_id, _thread, _time):
            if hwnd and object_id == 0 and child_id == 0:
                changed()
        hooks = [self.user.SetWinEventHook(first, last, None, event, 0, 0, 2)
                 for first, last in ((3, 3), (0x8001, 0x8003))]
        return [hook for hook in hooks if hook], event

    def unwatch_windows(self, hooks):
        for hook in hooks:
            self.user.UnhookWinEvent(hook)

    def renderer_above(self, hwnd):
        """Find the lowest overlapping Owl renderer; never alter its window.

        EnumWindows is in Z order. The bottommost matching surface keeps our SBS
        beneath both the mirror and any higher overlay, including at re-show.
        """
        rect = W.RECT()
        if not self.user.GetWindowRect(hwnd, C.byref(rect)):
            return None
        area = max(0, rect.right - rect.left) * max(0, rect.bottom - rect.top)
        matches, executables = [], {}

        @self.enum_type
        def visit(other, _):
            target = self.identity(other)
            if not target or target[1] == os.getpid() or not self.usable(target):
                return True
            bounds = W.RECT()
            if not self.user.GetWindowRect(other, C.byref(bounds)):
                return True
            overlap = (max(0, min(rect.right, bounds.right) - max(rect.left, bounds.left))
                       * max(0, min(rect.bottom, bounds.bottom) - max(rect.top, bounds.top)))
            if not area or overlap < area * .8:
                return True
            pid = target[1]
            if pid not in executables:
                executables[pid] = self.image_name(pid)
            if executables[pid] == 'display-mirror.exe':
                matches.append(int(other))
            return True

        self.user.EnumWindows(visit, 0)
        return matches[-1] if matches else None

    def order(self, hwnd):
        foreground = self.foreground()
        identity = self.identity(foreground)
        # Put output below the lowest of our active controls and Owl's final
        # renderer. Merely removing TOPMOST would insert it above other normal
        # windows, potentially obscuring the very error dialog we want to show.
        targets = []
        if identity and identity[1] == os.getpid() and not self.belongs(foreground, hwnd):
            targets.append(foreground)
        renderer = self.renderer_above(hwnd)
        if renderer:
            targets.append(renderer)
        if not targets:
            self.place(hwnd, -1)  # HWND_TOPMOST; never raise each frame.
            return
        insert, current, seen = targets[0], targets[0], set()
        while current and current not in seen:
            seen.add(current)
            if current in targets:
                insert = current
            current = int(self.user.GetWindow(current, 2) or 0)  # GW_HWNDNEXT
        if not self.user.GetWindowLongPtrW(insert, -20) & TOPMOST:
            self.place(hwnd, -2)  # HWND_NOTOPMOST, no activation.
        self.place(hwnd, insert)
