"""Win32 source identities. Titles are UI-only; never diagnostics identifiers."""

from .messages import Message as M

import ctypes as C
from ctypes import wintypes as W
import os

user32 = C.WinDLL("user32", use_last_error=True)
dwmapi = C.WinDLL("dwmapi", use_last_error=True)
user32.IsWindow.argtypes = [W.HWND]
user32.IsIconic.argtypes = [W.HWND]
user32.IsWindowVisible.argtypes = [W.HWND]
user32.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
user32.GetWindowTextLengthW.argtypes = [W.HWND]
user32.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
user32.GetWindowRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
user32.SetPropW.argtypes = [W.HWND, W.LPCWSTR, W.HANDLE]
user32.GetPropW.argtypes = [W.HWND, W.LPCWSTR]
user32.GetPropW.restype = W.HANDLE
SBS_OUTPUT_PROPERTY = "DepthSBS.OutputWindow.v1"


def is_sbs_output(hwnd):
    """Cross-process output marker; independent of mutable window titles."""
    return bool(user32.GetPropW(int(hwnd), SBS_OUTPUT_PROPERTY))


def mark_sbs_output(hwnd):
    pid = W.DWORD()
    user32.GetWindowThreadProcessId(int(hwnd), C.byref(pid))
    return pid.value == os.getpid() and bool(user32.SetPropW(int(hwnd), SBS_OUTPUT_PROPERTY, 1))
dwmapi.DwmGetWindowAttribute.argtypes = [W.HWND, W.DWORD, C.c_void_p, W.DWORD]


class MonitorInfo(C.Structure):
    _fields_ = [
        ("size", W.DWORD),
        ("rect", W.RECT),
        ("work", W.RECT),
        ("flags", W.DWORD),
        ("device", W.WCHAR * 32),
    ]


def monitors():
    rows = []
    callback_type = C.WINFUNCTYPE(
        W.BOOL, W.HMONITOR, W.HDC, C.POINTER(W.RECT), W.LPARAM
    )
    user32.GetMonitorInfoW.argtypes = [W.HMONITOR, C.POINTER(MonitorInfo)]

    @callback_type
    def callback(handle, dc, rect, data):
        info = MonitorInfo()
        info.size = C.sizeof(info)
        if user32.GetMonitorInfoW(handle, C.byref(info)):
            index = len(rows) + 1
            r = info.rect
            rows.append(
                dict(
                    kind="monitor",
                    id=index,
                    handle=int(handle),
                    device=info.device,
                    label=M('Monitor {v0} · {v1} × {v2}', v0=index, v1=r.right - r.left, v2=r.bottom - r.top),
                    width=r.right - r.left,
                    height=r.bottom - r.top,
                    x=r.left,
                    y=r.top,
                    pid=0,
                )
            )
        return True

    user32.EnumDisplayMonitors(None, None, callback, 0)
    return rows


def enable_capture_dpi():
    # The isolated process has no Qt application to establish DPI awareness.
    user32.SetProcessDpiAwarenessContext.argtypes = [C.c_void_p]
    user32.SetThreadDpiAwarenessContext.argtypes = [C.c_void_p]
    user32.SetThreadDpiAwarenessContext.restype = C.c_void_p
    user32.SetProcessDpiAwarenessContext(C.c_void_p(-4))
    if not user32.SetThreadDpiAwarenessContext(C.c_void_p(-4)):
        raise ValueError(M("Cannot set the capture worker's DPI coordinate system."))


def windows():
    rows = []
    callback_type = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)

    @callback_type
    def callback(hwnd, data):
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        pid = W.DWORD()
        user32.GetWindowThreadProcessId(hwnd, C.byref(pid))
        if pid.value == os.getpid() or is_sbs_output(hwnd):
            return True
        cloaked = W.DWORD()
        dwmapi.DwmGetWindowAttribute(hwnd, 14, C.byref(cloaked), C.sizeof(cloaked))
        length = user32.GetWindowTextLengthW(hwnd)
        if not length or cloaked.value:
            return True
        title = C.create_unicode_buffer(min(length + 1, 512))
        user32.GetWindowTextW(hwnd, title, len(title))
        rect = W.RECT()
        if not user32.GetWindowRect(hwnd, C.byref(rect)):
            return True
        if rect.right - rect.left < 16 or rect.bottom - rect.top < 16:
            return True
        rows.append(
            dict(
                kind="window",
                id=int(hwnd),
                pid=pid.value,
                label=title.value,
                width=rect.right - rect.left,
                height=rect.bottom - rect.top,
            )
        )
        return len(rows) < 256

    user32.EnumWindows(callback, 0)
    return rows


def validate_source(source):
    from .capture_color import require_sdr

    require_input_desktop()
    if source["kind"] == "monitor":
        current = monitors()
        if not any(
            r["id"] == source["id"]
            and r["device"] == source["device"]
            and r["width"] == source["width"]
            and r["height"] == source["height"]
            for r in current
        ):
            raise ValueError(
                M('The monitor configuration changed. Refresh the list and select it again.')
            )
    elif source["kind"] == "window":
        hwnd = source["id"]
        if is_sbs_output(hwnd):
            raise ValueError(M('An SBS output window cannot be used as input. Select the original game or video window.'))
        pid = W.DWORD()
        user32.GetWindowThreadProcessId(hwnd, C.byref(pid))
        if not user32.IsWindow(hwnd) or pid.value != source["pid"]:
            raise ValueError(M('The selected window closed. Select another window.'))
        if user32.IsIconic(hwnd) or not user32.IsWindowVisible(hwnd):
            raise ValueError(
                M('The selected window is minimized or hidden. Restore it, then restart.')
            )
    else:
        raise ValueError(M('Unsupported capture source.'))
    require_sdr(source)


def require_input_desktop():
    user32.OpenInputDesktop.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    user32.OpenInputDesktop.restype = W.HANDLE
    user32.CloseDesktop.argtypes = [W.HANDLE]
    user32.GetUserObjectInformationW.argtypes = [
        W.HANDLE,
        C.c_int,
        C.c_void_p,
        W.DWORD,
        C.POINTER(W.DWORD),
    ]
    handle = user32.OpenInputDesktop(0, False, 1)
    if not handle:
        raise ValueError(
            M('Capture stopped because the screen is locked or access is restricted. Unlock the screen, then restart.')
        )
    try:
        name = C.create_unicode_buffer(256)
        needed = W.DWORD()
        if (
            not user32.GetUserObjectInformationW(
                handle, 2, name, C.sizeof(name), C.byref(needed)
            )
            or name.value.casefold() != "default"
        ):
            raise ValueError(
                M('Capture is unavailable on a secure or unsupported desktop.')
            )
    finally:
        user32.CloseDesktop(handle)


def exclude_preview(hwnd):
    # WDA_EXCLUDEFROMCAPTURE prevents desktop feedback, only our own window.
    user32.SetWindowDisplayAffinity.argtypes = [W.HWND, W.DWORD]
    return bool(user32.SetWindowDisplayAffinity(int(hwnd), 0x11))


def set_output_affinity(hwnd, excluded):
    if not mark_sbs_output(hwnd):
        return False
    expected = 0x11 if excluded else 0
    actual = W.DWORD()
    user32.SetWindowDisplayAffinity.argtypes = [W.HWND, W.DWORD]
    user32.GetWindowDisplayAffinity.argtypes = [W.HWND, C.POINTER(W.DWORD)]
    return (bool(user32.SetWindowDisplayAffinity(int(hwnd), expected))
            and bool(user32.GetWindowDisplayAffinity(int(hwnd), C.byref(actual)))
            and actual.value == expected)
