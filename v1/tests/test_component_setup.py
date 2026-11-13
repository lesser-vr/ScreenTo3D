import unittest
import tempfile
import hashlib
import time
from pathlib import Path
from zipfile import ZipFile
from unittest.mock import Mock,patch
from PySide6.QtCore import QObject,QCoreApplication
from screento3d_app.model_downloads import ModelDownloads
from screento3d_app.desktop_jobs import ProcessingLease


class Desktop(QObject):
    def __init__(self):
        super().__init__();self.lease=ProcessingLease();self.closing=False;self.engine_paths={};self.values={'model':'da2-small'}
        self.changed=Mock();self.showModelError=Mock();self.gpuRuntimeKey='';self.live=None
    @property
    def busy(self):return bool(self.lease.owner)


class ComponentSetupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QCoreApplication.instance() or QCoreApplication([])
    def setUp(self):
        self.desktop=Desktop();self.downloads=ModelDownloads(self.desktop);self.missing={'trt-core','media-tools'}
        self.enterContext(patch.object(self.downloads,'needed',side_effect=lambda key:key in self.missing))
        self.begin=self.enterContext(patch.object(self.downloads,'begin'))
    def finish(self,key,message='',failed=False):
        self.downloads.active_key=key;self.desktop.lease.acquire('model-install')
        if not message:self.missing.discard(key)
        self.downloads._finished(key,message,failed);self.app.processEvents()
    def test_ordered_first_use_resumes_only_after_all_components_finish(self):
        resume=Mock();self.assertFalse(self.downloads.ensure(['trt-core','','trt-core','media-tools'],resume))
        self.begin.assert_called_once_with('trt-core',False)
        self.finish('trt-core');resume.assert_not_called();self.assertEqual(self.downloads.setupKey,'media-tools')
        self.finish('media-tools');resume.assert_called_once();self.assertFalse(self.downloads.setupVisible)
    def test_cancel_or_failure_discards_automatic_continuation(self):
        for failed in (True,False):
            self.missing.add('trt-core');resume=Mock();self.downloads.ensure(['trt-core'],resume)
            if not failed:self.downloads.cancel()
            self.finish('trt-core','Owned failure or cancellation',failed)
            resume.assert_not_called();self.assertIsNone(self.downloads.resume)
    def test_dismiss_or_app_close_never_starts_requested_task(self):
        resume=Mock();self.downloads.ensure(['trt-core'],resume);self.downloads.dismissSetup();self.app.processEvents()
        resume.assert_not_called();self.assertFalse(self.downloads.setupVisible)
        self.downloads.ensure(['trt-core'],resume);self.desktop.closing=True;self.desktop.exitReady=Mock()
        self.finish('trt-core');resume.assert_not_called()
    def test_ready_components_do_not_open_setup_or_run_callback(self):
        self.missing.clear();resume=Mock();self.assertTrue(self.downloads.ensure(['trt-core','media-tools'],resume))
        self.begin.assert_not_called();resume.assert_not_called()

    def test_dismiss_while_showing_setup_prevents_initial_download(self):
        def dismiss():
            if self.downloads.setupVisible:self.downloads.dismissSetup()
        self.downloads.changed.connect(dismiss)
        resume=Mock();self.downloads.ensure(['trt-core'],resume)
        self.begin.assert_not_called();resume.assert_not_called()
        self.assertFalse(self.downloads.setupVisible)

    def test_completion_hands_lease_to_next_task_before_returning(self):
        resume=Mock(side_effect=lambda:self.desktop.lease.acquire('live'))
        self.downloads.ensure(['trt-core'],resume);self.missing.discard('trt-core')
        self.desktop.lease.acquire('model-install');self.downloads._finished('trt-core','',False)
        self.assertEqual(self.desktop.lease.owner,'live');resume.assert_called_once()


class BrowserSetupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.desktop=Desktop();self.downloads=ModelDownloads(self.desktop)
        self.addCleanup(self.downloads.dismissSetup)
        self.missing={'trt-core'}
        self.enterContext(patch.object(self.downloads,'needed',side_effect=lambda key:key in self.missing))
        self.enterContext(patch('screento3d_app.model_downloads.source_for',side_effect=FileNotFoundError('No configured origin')))
        self.resume=Mock()

    def test_missing_origin_opens_download_guidance_without_error_or_worker(self):
        with patch.object(self.downloads,'_install') as install:
            self.assertFalse(self.downloads.ensure(['trt-core'],self.resume))
            self.assertTrue(self.downloads.setupVisible)
            self.assertEqual(self.downloads.setupKey,'trt-core')
            self.assertEqual(self.downloads.installAction('trt-core'),'Download in browser')
            self.assertIn('tensorrt-',self.downloads.downloadHelp('trt-core'))
            self.desktop.showModelError.assert_not_called();install.assert_not_called()
            self.assertFalse(self.desktop.busy);self.resume.assert_not_called()

    def start_browser(self,directory):
        from screento3d_app.optional_models import PACKS
        self.downloads.ensure(['trt-core'],self.resume)
        with patch('screento3d_app.model_downloads.QStandardPaths.writableLocation',return_value=str(directory)),\
             patch('screento3d_app.model_downloads.QDesktopServices.openUrl',return_value=True) as opened:
            self.downloads.downloadInBrowser('trt-core')
            self.assertTrue(opened.call_args.args[0].toString().endswith('/'+PACKS['trt-core'].filename))

    def test_completed_browser_file_enters_existing_verified_installer(self):
        from screento3d_app.optional_models import PACKS,Pack
        with tempfile.TemporaryDirectory() as directory,patch.dict(PACKS,{'trt-core':Pack('Fixture','fixture.zip',4,'unused','')}):
            self.start_browser(directory)
            self.assertEqual(self.downloads.waitingKey,'trt-core')
            path=Path(directory)/'fixture.zip';path.write_bytes(b'pack')
            with patch.object(self.downloads,'_install') as install:
                self.downloads._downloadReady();install.assert_not_called()
                self.downloads._downloadReady();install.assert_called_once_with('trt-core',path)
            self.assertFalse(self.downloads.download_timer.isActive())
            self.resume.assert_not_called()  # File detection alone is never installation success.
            self.desktop.showModelError.assert_not_called()

    def test_cancel_close_or_timeout_prevents_late_install_and_resume(self):
        for action in ('cancel','dismiss','timeout'):
            with self.subTest(action=action),tempfile.TemporaryDirectory() as directory:
                self.start_browser(directory)
                if action=='cancel':self.downloads.cancel()
                elif action=='dismiss':self.downloads.dismissSetup()
                else:
                    self.downloads.handoff.deadline=0
                    self.downloads._downloadReady()
                with patch.object(self.downloads,'_install') as install:
                    self.downloads._downloadReady();install.assert_not_called()
                self.assertFalse(self.downloads.download_timer.isActive())
                self.assertIsNone(self.downloads.resume);self.assertFalse(self.downloads.waitingKey)
                self.resume.assert_not_called();self.desktop.showModelError.assert_not_called()

    def test_repeated_start_does_not_replace_pending_selection(self):
        self.downloads.ensure(['trt-core'],self.resume)
        other=Mock();self.downloads.ensure(['trt-core'],other)
        self.assertIs(self.downloads.resume,self.resume)
        self.missing.add('media-tools')
        with patch.object(self.downloads,'_install') as install,\
             patch('screento3d_app.model_downloads.QDesktopServices.openUrl') as opened:
            self.downloads.begin('media-tools',False)
            self.downloads.downloadInBrowser('media-tools')
            install.assert_not_called();opened.assert_not_called()
            self.assertEqual(self.downloads.setupKey,'trt-core')

    def test_invalid_configured_origin_and_browser_launch_failure_are_real_errors(self):
        with patch('screento3d_app.model_downloads.source_for',side_effect=ValueError('Invalid HTTPS origin')):
            self.downloads.begin('trt-core',False)
            self.desktop.showModelError.assert_called_once()
        self.desktop.showModelError.reset_mock()
        self.downloads.ensure(['trt-core'],self.resume)
        with patch('screento3d_app.model_downloads.QStandardPaths.writableLocation',return_value='Downloads'),\
             patch('screento3d_app.model_downloads.QDesktopServices.openUrl',return_value=False):
            self.downloads.downloadInBrowser('trt-core')
        self.desktop.showModelError.assert_called_once()
        self.assertFalse(self.downloads.download_timer.isActive())
        self.assertIsNone(self.downloads.resume)

    def test_browser_handoff_verifies_payload_before_resume_and_rejects_corruption(self):
        from screento3d_app import optional_models as models,desktop_runtimes as runtimes
        for corrupt in (False,True):
            with self.subTest(corrupt=corrupt),tempfile.TemporaryDirectory() as directory:
                self.downloads.dismissSetup();self.desktop.showModelError.reset_mock();self.resume.reset_mock()
                root=Path(directory);archive=root/'fixture.zip';payload=b'owned library fixture'
                with ZipFile(archive,'w') as zip:zip.writestr('owned.dll',payload)
                data=archive.read_bytes();sha=hashlib.sha256(data).hexdigest()
                pin=dict(filename=archive.name,size=len(data),sha=sha,
                         files={'owned.dll':dict(bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest())})
                target=root/'cache/version'
                if corrupt:archive.write_bytes(bytes([data[0]^1])+data[1:])
                with patch.dict(runtimes.PACKS,{'trt-core':pin}),\
                     patch.dict(models.PACKS,{'trt-core':models.Pack('Fixture',archive.name,len(data),sha,'')}),\
                     patch('screento3d_app.model_downloads.installed_path',return_value=target),\
                     patch.object(self.downloads,'needed',side_effect=lambda key:key=='trt-core' and not models.available(key,target)):
                    self.start_browser(directory)
                    self.downloads._downloadReady();self.downloads._downloadReady()
                    deadline=time.monotonic()+5
                    while self.downloads.active_key and time.monotonic()<deadline:
                        self.app.processEvents();time.sleep(.005)
                    self.assertFalse(self.downloads.active_key)
                    self.assertFalse(self.desktop.busy)
                    if corrupt:
                        self.assertFalse(target.exists());self.resume.assert_not_called()
                        self.desktop.showModelError.assert_called_once()
                    else:
                        self.assertEqual((target/'owned.dll').read_bytes(),payload)
                        self.resume.assert_called_once();self.desktop.showModelError.assert_not_called()


class DownloadHandoffTests(unittest.TestCase):
    def test_only_stable_completed_named_files_are_accepted_and_wait_is_bounded(self):
        from screento3d_app.browser_download import DownloadHandoff,release_url
        with tempfile.TemporaryDirectory() as directory:
            handoff=DownloadHandoff(directory,'pack.zip',4,0)
            root=Path(directory)
            (root/'pack.zip.crdownload').write_bytes(b'pack')
            (root/'unrelated.zip').write_bytes(b'pack')
            (root/'pack.zip').write_bytes(b'bad')
            self.assertIsNone(handoff.ready(1));self.assertIsNone(handoff.ready(2))
            path=root/'pack (1).zip';path.write_bytes(b'pack')
            self.assertIsNone(handoff.ready(3));self.assertEqual(handoff.ready(4),path)
            with self.assertRaises(TimeoutError):handoff.ready(901)
        with self.assertRaises(ValueError):release_url('../private-file')


if __name__=='__main__':unittest.main()
