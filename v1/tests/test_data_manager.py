"""Exercise GUI import ownership without touching real registry or model files."""
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock,patch

from PySide6.QtCore import QObject,QCoreApplication,QSettings
from screento3d_app.data_manager import DataManager
from screento3d_app.desktop_jobs import ProcessingLease
from screento3d_app.desktop_preferences import DesktopPreferences


class Desktop(QObject):
    def __init__(self,root):
        super().__init__();self.lease=ProcessingLease();self.closing=False
        self.preferences=DesktopPreferences(QSettings(str(root/'settings.ini'),QSettings.IniFormat))
        self.changed=Mock();self.showModelError=Mock();self.exitReady=Mock();self.refreshImportedData=Mock()
    @property
    def busy(self):return bool(self.lease.owner)


class DataManagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QCoreApplication.instance() or QCoreApplication([])
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup);self.root=Path(folder.name)
        self.desktop=Desktop(self.root);self.manager=DataManager(self.desktop)
        self.enterContext(patch('screento3d_app.user_data.APP_ROOT',self.root/'app'))
        self.enterContext(patch('screento3d_app.data_manager.legacy_roots',return_value=[self.root/'old']))
    def wait(self):
        deadline=time.monotonic()+5
        while self.manager.active and time.monotonic()<deadline:self.app.processEvents();time.sleep(.005)
        self.assertFalse(self.manager.active)
    def test_offer_only_inventories_and_dismiss_is_persisted_without_registry_read(self):
        with patch('screento3d_app.portable_settings.read_legacy_settings') as read,\
             patch('screento3d_app.data_manager.import_files') as copy:
            self.manager.offer();self.assertTrue(self.manager.shown)
            read.assert_not_called();copy.assert_not_called()
            self.manager.dismiss();self.manager.offer();self.assertFalse(self.manager.shown)
    def test_success_imports_missing_settings_releases_lease_and_refreshes(self):
        self.desktop.preferences.store.setValue('ui/language','en')
        report=dict(files=1,conflicts=0,removed=0,preserved=1)
        with patch('screento3d_app.portable_settings.read_legacy_settings',return_value={'ui/language':'ko','live/model':'da2-base'}),\
             patch('screento3d_app.data_manager.import_files',return_value=report) as copy:
            self.manager.begin(True,False);self.assertEqual(self.desktop.lease.owner,'data-import');self.wait()
            self.assertFalse(copy.call_args.kwargs['cleanup'])
            self.assertEqual(self.desktop.preferences.store.value('ui/language'),'en')
            self.assertEqual(self.desktop.preferences.store.value('live/model'),'da2-base')
            self.desktop.refreshImportedData.assert_called_once();self.assertFalse(self.desktop.busy)
    def test_cancel_waits_for_owned_worker_and_close_signal(self):
        entered=threading.Event()
        def copy(items,progress,cancelled,**kwargs):
            entered.set()
            while not cancelled():time.sleep(.005)
            from screento3d_app.messages import ErrorMessage
            raise InterruptedError(ErrorMessage('E_DATA_IMPORT_CANCELLED'))
        with patch('screento3d_app.portable_settings.read_legacy_settings') as read,\
             patch('screento3d_app.data_manager.import_files',side_effect=copy):
            self.manager.begin(False,False);self.assertTrue(entered.wait(2))
            self.desktop.closing=True;self.manager.dismiss()
            self.assertTrue(self.manager.active);self.assertTrue(self.desktop.busy)
            self.wait();self.assertFalse(self.desktop.busy);self.desktop.exitReady.emit.assert_called_once()
            self.desktop.showModelError.assert_not_called();read.assert_not_called()
    def test_copy_failure_preserves_settings_and_reports_owned_error(self):
        with patch('screento3d_app.portable_settings.read_legacy_settings',return_value={'ui/language':'ko'}),\
             patch('screento3d_app.data_manager.import_files',side_effect=OSError('fixture failure')):
            self.manager.begin(True,False);self.wait()
            self.assertFalse(self.desktop.preferences.store.contains('ui/language'))
            self.desktop.refreshImportedData.assert_not_called();self.desktop.showModelError.assert_called_once()
            self.assertFalse(self.desktop.busy)


if __name__=='__main__':unittest.main()
