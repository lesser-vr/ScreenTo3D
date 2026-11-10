"""Read-only Windows advanced-color policy. Unknown/HDR is not silently SDR."""

from .messages import Message as M

import ctypes as C
from ctypes import wintypes as W
import struct


class Luid(C.Structure):
    _fields_ = [("low", W.DWORD), ("high", W.LONG)]


class Header(C.Structure):
    _fields_ = [
        ("kind", W.DWORD),
        ("size", W.DWORD),
        ("adapter", Luid),
        ("id", W.DWORD),
    ]


class SourceName(C.Structure):
    _fields_ = [("header", Header), ("name", W.WCHAR * 32)]


class ColorInfo(C.Structure):
    _fields_ = [
        ("header", Header),
        ("flags", W.DWORD),
        ("encoding", W.DWORD),
        ("bits", W.DWORD),
    ]


def display_colors():
    user = C.WinDLL("user32")
    paths, modes = W.UINT(), W.UINT()
    if user.GetDisplayConfigBufferSizes(2, C.byref(paths), C.byref(modes)) != 0:
        raise ValueError(
            M('Cannot read display color information. This configuration needs compatibility validation.')
        )
    if not 0 < paths.value <= 64 or modes.value > 256:
        raise ValueError(M('Unsupported display configuration.'))
    # ABI: DISPLAYCONFIG_PATH_INFO=72, MODE_INFO=64; extract only named IDs.
    path_data = (C.c_ubyte * (paths.value * 72))()
    mode_data = (C.c_ubyte * (max(1, modes.value) * 64))()
    if (
        user.QueryDisplayConfig(
            2, C.byref(paths), path_data, C.byref(modes), mode_data, None
        )
        != 0
    ):
        raise ValueError(M('The display configuration changed. Try again.'))
    result = {}
    data = bytes(path_data)
    for index in range(paths.value):
        row = data[index * 72 : (index + 1) * 72]
        low, high, source_id = struct.unpack_from("<IiI", row, 0)
        source = SourceName(Header(1, C.sizeof(SourceName), Luid(low, high), source_id))
        if user.DisplayConfigGetDeviceInfo(C.byref(source)) != 0:
            raise ValueError(M('Cannot identify the display.'))
        low, high, target_id = struct.unpack_from("<IiI", row, 20)
        info = ColorInfo(Header(9, C.sizeof(ColorInfo), Luid(low, high), target_id))
        if user.DisplayConfigGetDeviceInfo(C.byref(info)) != 0:
            raise ValueError(M('Cannot read HDR or advanced color status.'))
        result[source.name] = dict(enabled=bool(info.flags & 2), bits=info.bits)
    return result


def require_sdr(source):
    from .capture_sources import user32, MonitorInfo

    if source["kind"] == "monitor":
        device = source["device"]
    else:
        user32.MonitorFromWindow.argtypes = [W.HWND, W.DWORD]
        user32.MonitorFromWindow.restype = W.HMONITOR
        handle = user32.MonitorFromWindow(source["id"], 2)
        info = MonitorInfo()
        info.size = C.sizeof(info)
        user32.GetMonitorInfoW.argtypes = [W.HMONITOR, C.POINTER(MonitorInfo)]
        if not user32.GetMonitorInfoW(handle, C.byref(info)):
            raise ValueError(M('Cannot identify the display containing this window.'))
        device = info.device
    colors = display_colors()
    if source["kind"] == "window" and any(c["enabled"] for c in colors.values()):
        raise ValueError(
            M('Window capture requires all connected displays to use SDR. Mixed HDR configurations have not been validated.')
        )
    color = colors.get(device)
    if color is None or color["enabled"]:
        raise ValueError(
            M('This preview supports SDR only. Turn off HDR and advanced color, then restart.')
        )
