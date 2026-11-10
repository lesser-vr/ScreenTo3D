"""Window-level shell identity for Python-hosted Windows desktop windows."""
import ctypes as ct
import sys
import uuid

APP_ID = "ScreenTo3D.Desktop"


class PropertyKey(ct.Structure):
    _fields_ = [("format", ct.c_ubyte * 16), ("pid", ct.c_ulong)]


class Value(ct.Union):
    _fields_ = [("text", ct.c_wchar_p), ("storage", ct.c_ulonglong * 2)]


class PropVariant(ct.Structure):
    _fields_ = [("vt", ct.c_ushort), ("reserved", ct.c_ushort * 3), ("value", Value)]


def _check(status):
    if status < 0:
        raise OSError(f"Windows taskbar identity failed: HRESULT 0x{status & 0xffffffff:08x}")


def set_window_identity(hwnd, executable, icon):
    """Set relaunch properties before ID so the shell can resolve the whole group."""
    shell = ct.WinDLL("shell32")
    get_store = shell.SHGetPropertyStoreForWindow
    get_store.argtypes = [ct.c_void_p, ct.c_void_p, ct.POINTER(ct.c_void_p)]
    get_store.restype = ct.c_long
    iid = (ct.c_ubyte * 16).from_buffer_copy(uuid.UUID("886d8eeb-8cf2-4446-8d02-cdba1dbdcf99").bytes_le)
    store = ct.c_void_p()
    _check(get_store(hwnd, ct.byref(iid), ct.byref(store)))
    table = ct.cast(store, ct.POINTER(ct.POINTER(ct.c_void_p))).contents
    set_value = ct.WINFUNCTYPE(ct.c_long, ct.c_void_p, ct.POINTER(PropertyKey), ct.POINTER(PropVariant))(table[6])
    release = ct.WINFUNCTYPE(ct.c_ulong, ct.c_void_p)(table[2])
    values = [(3, str(icon) + ",0")]
    if executable.is_file():
        values += [(2, '"' + str(executable) + '"'), (4, "ScreenTo3D")]
    values += [(5, APP_ID)]
    try:
        for pid, text in values:
            key = PropertyKey((ct.c_ubyte * 16).from_buffer_copy(
                uuid.UUID("9f4c2855-9f79-4b39-a8d0-e1d42de1d5f3").bytes_le), pid)
            variant = PropVariant()
            variant.vt = 31  # VT_LPWSTR; SetValue copies this Python-owned string.
            variant.value.text = text
            _check(set_value(store, ct.byref(key), ct.byref(variant)))
    finally:
        release(store)


def attach(window):
    if sys.platform != "win32":
        return
    from pathlib import Path
    from PySide6.QtCore import QObject, QEvent
    from PySide6.QtGui import QPlatformSurfaceEvent
    from .desktop_jobs import ROOT

    class IdentityFilter(QObject):
        def apply(self):
            set_window_identity(int(window.winId()), ROOT / "ScreenTo3D.exe",
                                Path(__file__).with_name("assets") / "depthsbs.ico")

        def eventFilter(self, watched, event):
            if (event.type() == QEvent.PlatformSurface
                    and event.surfaceEventType() == QPlatformSurfaceEvent.SurfaceCreated):
                self.apply()
            return False

    watcher = IdentityFilter(window)
    window._taskbar_identity = watcher
    window.installEventFilter(watcher)
    watcher.apply()
