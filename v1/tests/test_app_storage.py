"""Portable storage controls preserve current and external data without migration."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from screento3d_app import user_data
from screento3d_app.desktop import DesktopController
from screento3d_app.desktop_preferences import DesktopPreferences


class AppStorageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.base = Path(folder.name)
        self.root = self.base / 'portable'
        self.root.mkdir()
        self.local = self.base / 'previous-appdata'
        self.enterContext(patch.object(user_data, 'APP_ROOT', self.root))
        self.enterContext(patch.dict(os.environ, {'LOCALAPPDATA': str(self.local)}))
        self.preferences = DesktopPreferences(QSettings(str(self.root/'data/settings.ini'), QSettings.IniFormat))

    def controller(self):
        desktop = DesktopController(self.preferences)
        self.addCleanup(desktop.deleteLater)
        return desktop

    def test_data_folder_control_opens_current_app_location_only(self):
        desktop = self.controller()
        self.assertEqual(Path(desktop.dataPath), self.root/'data')
        with patch('screento3d_app.desktop.QDesktopServices.openUrl', return_value=True) as opened:
            desktop.openDataFolder()
        opened.assert_called_once()
        self.assertEqual(Path(opened.call_args.args[0].toLocalFile()), self.root/'data')
        self.assertFalse(desktop.busy)
        self.assertFalse(self.local.exists())

    def test_startup_ignores_previous_data_and_preserves_current_preferences(self):
        files = []
        for name in ('ScreenTo3D', 'StereoTo3D', 'DepthSBS'):
            path = self.local/name/'models/retained.plan'
            path.parent.mkdir(parents=True)
            path.write_bytes(b'existing external model')
            files.append(path)
        self.preferences.remember('live', 'balanced', 'da2-base', 'half-sbs')
        self.preferences.store.setValue('ui/language', 'ko')
        self.preferences.store.sync()
        original = (self.root/'data/settings.ini').read_bytes()
        iterdir = Path.iterdir
        def guard(path):
            if path.is_relative_to(self.local):
                raise AssertionError('Startup scanned previous app data')
            return iterdir(path)
        with patch.object(Path, 'iterdir', guard):
            desktop = self.controller()
            self.app.processEvents()
        self.assertFalse(desktop.busy)
        self.assertEqual((self.root/'data/settings.ini').read_bytes(), original)
        self.assertEqual(self.preferences.selection('live', {'balanced', 'performance'}),
                         dict(mode='balanced', model='da2-base', stereo_layout='half-sbs'))
        for path in files:
            self.assertEqual(path.read_bytes(), b'existing external model')
        self.assertFalse((self.root/'data/models').exists())


if __name__ == '__main__':
    unittest.main()
