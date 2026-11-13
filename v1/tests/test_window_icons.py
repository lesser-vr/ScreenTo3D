"""Native icon conversion and source-identity guards; no screen capture."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QIcon, QImage, QPixmap, QWindow
from PySide6.QtWidgets import QApplication
from screento3d_app.window_icons import WindowIcons, window_icon

APP = QApplication.instance() or QApplication([])


class WindowIconTests(unittest.TestCase):
    def test_real_owned_window_icon_and_pid_guard(self):
        window = QWindow()
        pixels = QPixmap(32, 32)
        pixels.fill(QColor('#1267ab'))
        window.setIcon(QIcon(pixels))
        try:
            hwnd = int(window.winId())
            result = window_icon(hwnd, os.getpid())
            self.assertFalse(result.isNull())
            self.assertEqual(result.pixelColor(result.width()//2, result.height()//2).name(), '#1267ab')
            self.assertTrue(window_icon(hwnd, os.getpid() + 1).isNull())
        finally:
            window.destroy()

    def test_unselected_or_unrelated_request_never_reads_window(self):
        live = SimpleNamespace(items=[dict(kind='window', id=1, pid=2)], selected=-1)
        provider = WindowIcons(live)
        with patch('screento3d_app.window_icons.window_icon') as read:
            result = provider.requestImage('1/2', QSize(), QSize())
            self.assertEqual(result.size(), QSize(1, 1))
            live.selected = 0
            provider.requestImage('99/2', QSize(), QSize())
            read.assert_not_called()

    def test_single_icon_cache_changes_with_process_identity(self):
        live = SimpleNamespace(items=[dict(kind='window', id=1, pid=2)], selected=0)
        provider = WindowIcons(live)
        image = QImage(32, 32, QImage.Format_ARGB32)
        image.fill(QColor('blue'))
        with patch('screento3d_app.window_icons.window_icon', return_value=image) as read:
            provider.requestImage('1/2', QSize(), QSize())
            provider.requestImage('1/2', QSize(), QSize())
            self.assertEqual(read.call_count, 1)
            live.items[0]['pid'] = 3
            provider.requestImage('1/3', QSize(), QSize())
            self.assertEqual(read.call_count, 2)


if __name__ == '__main__':
    unittest.main()
