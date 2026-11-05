"""Read selected-window application icons, never client pixels or thumbnails."""
import ctypes as C
from ctypes import wintypes as W

from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickImageProvider


def window_icon(hwnd, pid):
    user32 = C.WinDLL("user32", use_last_error=True)
    user32.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
    actual_pid = W.DWORD()
    user32.GetWindowThreadProcessId(hwnd, C.byref(actual_pid))
    if actual_pid.value != pid:
        return QImage()
    user32.SendMessageTimeoutW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM,
                                         W.UINT, W.UINT, C.POINTER(C.c_size_t)]
    user32.SendMessageTimeoutW.restype = W.LPARAM
    user32.GetClassLongPtrW.argtypes = [W.HWND, C.c_int]
    user32.GetClassLongPtrW.restype = C.c_size_t
    user32.CopyIcon.argtypes = [W.HICON]
    user32.CopyIcon.restype = W.HICON
    user32.DestroyIcon.argtypes = [W.HICON]
    handle = C.c_size_t()
    # One bounded request: a hung application cannot freeze the source selector.
    user32.SendMessageTimeoutW(hwnd, 0x7F, 1, 0, 0x2, 40, C.byref(handle))
    borrowed = handle.value or user32.GetClassLongPtrW(hwnd, -14)
    owned = user32.CopyIcon(borrowed) if borrowed else None
    if not owned:
        return QImage()
    try:
        return QImage.fromHICON(owned)
    finally:
        user32.DestroyIcon(owned)


class WindowIcons(QQuickImageProvider):
    def __init__(self, live):
        super().__init__(QQuickImageProvider.Image)
        self.live = live
        self.cached_key = None
        self.cached_image = QImage()

    def requestImage(self, identifier, size, requestedSize):
        rows = self.live.items
        index = self.live.selected
        row = rows[index] if 0 <= index < len(rows) else {}
        key = f"{row.get('id', 0)}/{row.get('pid', 0)}"
        if identifier != key or row.get('kind') != 'window':
            result = QImage()
        else:
            if key != self.cached_key:
                self.cached_key = key
                self.cached_image = window_icon(row['id'], row['pid'])
            result = self.cached_image
        # A transparent image avoids Qt failed-image warnings for iconless apps.
        if result.isNull():
            result = QImage(1, 1, QImage.Format_ARGB32)
            result.fill(0)
        size.setWidth(result.width()); size.setHeight(result.height())
        return result
