from ctypes import wintypes as wt
import ctypes as ct

from screento3d_app.live_preview import LivePreview


class OwlOutputLive(LivePreview):
    def configureOutputCapture(self, window):
        # Only this owned SBS output is exposed to the user's Owl3D compositor.
        # Main/tools/errors retain the normal application's capture exclusion.
        from screento3d_app.capture_sources import mark_sbs_output, user32

        self.output_excluded = False
        hwnd = int(window.winId())
        if not mark_sbs_output(hwnd):
            return False
        user32.SetWindowDisplayAffinity.argtypes = [wt.HWND, wt.DWORD]
        user32.GetWindowDisplayAffinity.argtypes = [wt.HWND, ct.POINTER(wt.DWORD)]
        affinity = wt.DWORD(0xFFFFFFFF)
        return (bool(user32.SetWindowDisplayAffinity(hwnd, 0))
                and bool(user32.GetWindowDisplayAffinity(hwnd, ct.byref(affinity)))
                and affinity.value == 0)
