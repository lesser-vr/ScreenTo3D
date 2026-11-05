"""Win32 source identities. Titles are UI-only; never diagnostics identifiers."""

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
                    label=f"모니터 {index} · {r.right - r.left} × {r.bottom - r.top}",
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
        raise ValueError("캡처 작업의 DPI 좌표계를 설정하지 못했습니다.")


def windows():
    rows = []
    callback_type = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)

    @callback_type
    def callback(hwnd, data):
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        pid = W.DWORD()
        user32.GetWindowThreadProcessId(hwnd, C.byref(pid))
        if pid.value == os.getpid():
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
                "모니터 구성이 바뀌었습니다. 목록을 새로고침하고 다시 선택하세요."
            )
    elif source["kind"] == "window":
        hwnd = source["id"]
        pid = W.DWORD()
        user32.GetWindowThreadProcessId(hwnd, C.byref(pid))
        if not user32.IsWindow(hwnd) or pid.value != source["pid"]:
            raise ValueError("선택한 창이 종료되었습니다. 다시 선택하세요.")
        if user32.IsIconic(hwnd) or not user32.IsWindowVisible(hwnd):
            raise ValueError(
                "선택한 창이 최소화되거나 숨겨졌습니다. 복원한 뒤 다시 시작하세요."
            )
    else:
        raise ValueError("지원하지 않는 캡처 대상입니다.")
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
            "화면 잠금 또는 접근 제한으로 캡처를 중단합니다. 잠금을 해제한 뒤 다시 시작하세요."
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
                "보안 화면 또는 지원하지 않는 데스크톱에서는 캡처할 수 없습니다."
            )
    finally:
        user32.CloseDesktop(handle)


def exclude_preview(hwnd):
    # WDA_EXCLUDEFROMCAPTURE prevents desktop feedback, only our own window.
    user32.SetWindowDisplayAffinity.argtypes = [W.HWND, W.DWORD]
    return bool(user32.SetWindowDisplayAffinity(int(hwnd), 0x11))
