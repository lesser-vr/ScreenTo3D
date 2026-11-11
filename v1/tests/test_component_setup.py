import unittest
from unittest.mock import Mock,patch
from PySide6.QtCore import QObject,QCoreApplication
from depthsbs_app.model_downloads import ModelDownloads
from depthsbs_app.desktop_jobs import ProcessingLease


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

    def test_completion_hands_lease_to_next_task_before_returning(self):
        resume=Mock(side_effect=lambda:self.desktop.lease.acquire('live'))
        self.downloads.ensure(['trt-core'],resume);self.missing.discard('trt-core')
        self.desktop.lease.acquire('model-install');self.downloads._finished('trt-core','',False)
        self.assertEqual(self.desktop.lease.owner,'live');resume.assert_called_once()


if __name__=='__main__':unittest.main()
