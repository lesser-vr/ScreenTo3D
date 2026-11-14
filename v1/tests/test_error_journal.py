"""Dialog errors must survive dismissal and preserve their stable identity."""
import contextlib,io,json,tempfile,unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtQuick import QQuickWindow
from screento3d_app.error_dialog import LiveErrorDialog
from screento3d_app.messages import ErrorMessage as E

class ErrorDialogJournalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_dismissed_error_and_nested_diagnostic_remain_on_disk(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);owner=QQuickWindow();dialog=LiveErrorDialog(owner)
            try:
                error=E('E_OUTPUT_FRAME_DELIVERY',v0=E('E_CAPTURE_SOURCE_CLOSED'),details='driver code 17 / 한글 경로')
                with patch('screento3d_app.user_data.data_root',return_value=root),patch('screento3d_app.capture_sources.exclude_preview',return_value=True):
                    self.assertTrue(dialog.showError(error));shown=dialog.text.toPlainText();dialog.close()
                    dialog.retranslate()
                entries=[json.loads(line) for line in (root/'logs/errors.jsonl').read_text(encoding='utf-8').splitlines()]
                self.assertEqual(len(entries),1)
                entry=entries[0]
                self.assertEqual(entry['error_id'],'E_OUTPUT_FRAME_DELIVERY')
                self.assertEqual(entry['details'],'driver code 17 / 한글 경로')
                self.assertEqual(entry['displayed_text'],shown)
                self.assertEqual(entry['error']['values']['v0']['error_id'],'E_CAPTURE_SOURCE_CLOSED')
                self.assertIn('timestamp',entry)
            finally:dialog.close();dialog.deleteLater();owner.deleteLater();self.app.processEvents()

    def test_capture_protection_failure_still_records_error(self):
        with tempfile.TemporaryDirectory() as folder:
            owner=QQuickWindow();dialog=LiveErrorDialog(owner)
            try:
                with patch('screento3d_app.user_data.data_root',return_value=Path(folder)),patch('screento3d_app.capture_sources.exclude_preview',return_value=False):
                    self.assertFalse(dialog.showError(E('E_CAPTURE_SOURCE_CLOSED')))
                self.assertFalse(dialog.isVisible())
                entry=json.loads((Path(folder)/'logs/errors.jsonl').read_text(encoding='utf-8'))
                self.assertEqual(entry['error_id'],'E_CAPTURE_SOURCE_CLOSED')
            finally:dialog.close();dialog.deleteLater();owner.deleteLater();self.app.processEvents()

    def test_unwritable_history_does_not_suppress_original_window(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'logs').write_text('owned sentinel',encoding='utf-8')
            owner=QQuickWindow();dialog=LiveErrorDialog(owner)
            try:
                with contextlib.redirect_stderr(io.StringIO()),patch('screento3d_app.user_data.data_root',return_value=root),patch('screento3d_app.capture_sources.exclude_preview',return_value=True):
                    self.assertTrue(dialog.showError(E('E_UNKNOWN',details='original driver error 17')))
                self.assertTrue(dialog.isVisible())
                self.assertIn('original driver error 17',dialog.text.toPlainText())
                self.assertEqual((root/'logs').read_text(encoding='utf-8'),'owned sentinel')
            finally:dialog.close();dialog.deleteLater();owner.deleteLater();self.app.processEvents()


class ErrorJournalTests(unittest.TestCase):
    def setUp(self):
        from screento3d_app.error_journal import record_error
        self.record=record_error
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        location=patch('screento3d_app.user_data.data_root',return_value=self.root);location.start();self.addCleanup(location.stop)

    def save(self,error):
        return self.record(error,title='3D 오류',message=str(error),displayed_text='오류 ID: '+error.error_id+'\n'+error.details)

    def entries(self,name='errors.jsonl'):
        return [json.loads(line) for line in (self.root/'logs'/name).read_text(encoding='utf-8').splitlines()]

    def test_independent_reports_append_with_timezone_and_launch_correlation(self):
        with patch.dict('os.environ',{'SCREENTO3D_LAUNCH_LOG':'/private/path/launch-17.log'}):
            self.assertTrue(self.save(E('E_CAPTURE_SOURCE_CLOSED')))
            self.assertTrue(self.save(E('E_UNKNOWN',details='한글 경로\ncode 17')))
        entries=self.entries();self.assertEqual(len(entries),2)
        self.assertEqual([r['error_id'] for r in entries],['E_CAPTURE_SOURCE_CLOSED','E_UNKNOWN'])
        self.assertEqual(entries[-1]['details'],'한글 경로\ncode 17')
        self.assertEqual(entries[-1]['launch_log'],'launch-17.log')
        self.assertNotIn('/private/path',json.dumps(entries))
        self.assertIsNotNone(datetime.fromisoformat(entries[0]['timestamp']).utcoffset())
        self.assertGreater(entries[0]['pid'],0)
        self.assertFalse(entries[0]['truncated'])

    def test_rotation_preserves_latest_reports_and_one_backup(self):
        self.assertTrue(self.save(E('E_UNKNOWN',details='case-0 '+('한글'*30))))
        maximum=(self.root/'logs/errors.jsonl').stat().st_size*2+128
        with patch('screento3d_app.error_journal.MAX_LOG_BYTES',maximum):
            for index in range(1,14):self.assertTrue(self.save(E('E_UNKNOWN',details=f'case-{index} '+('한글'*30))))
        current=self.entries();previous=self.entries('errors.1.jsonl')
        self.assertTrue(current and previous)
        self.assertTrue(current[-1]['details'].startswith('case-13 '))
        self.assertEqual({p.name for p in (self.root/'logs').iterdir()},{'errors.jsonl','errors.1.jsonl'})
        for p in (self.root/'logs').iterdir():self.assertLessEqual(p.stat().st_size,maximum)

    def test_large_nested_report_remains_valid_and_keeps_error_id(self):
        from screento3d_app.error_journal import MAX_RECORD_BYTES
        error_id='E_'+('A'*79)
        error=E(error_id,details='한글'*30000,**{f'v{i}':'𐍈'*4096 for i in range(64)})
        self.assertTrue(self.save(error))
        path=self.root/'logs/errors.jsonl';self.assertLessEqual(path.stat().st_size,MAX_RECORD_BYTES)
        value=self.entries()[0];self.assertEqual(value['error_id'],error_id)
        self.assertEqual(value['error']['error_id'],error_id)
        self.assertTrue(value['truncated'])

    def test_nonfinite_parameters_and_legacy_errors_are_recordable(self):
        self.assertTrue(self.save(E('E_UNKNOWN',v0=float('nan'))))
        self.assertTrue(self.record(ValueError('opaque native error'),title='error',message='shown',displayed_text='shown'))
        self.assertEqual(self.entries()[0]['error']['values']['v0'],'nan')
        self.assertEqual(self.entries()[1]['details'],'opaque native error')

    def test_storage_failure_returns_false_without_replacing_existing_file(self):
        (self.root/'logs').write_text('sentinel',encoding='utf-8')
        trace=io.StringIO()
        with contextlib.redirect_stderr(trace):self.assertFalse(self.save(E('E_UNKNOWN',details='secret diagnostic')))
        self.assertIn('E_UNKNOWN',trace.getvalue());self.assertNotIn('secret diagnostic',trace.getvalue())
        self.assertEqual((self.root/'logs').read_text(encoding='utf-8'),'sentinel')

    def test_redirected_log_path_is_rejected_before_write(self):
        self.root.joinpath('logs').mkdir()
        with tempfile.TemporaryDirectory() as outside:
            target=Path(outside)/'sentinel';target.write_text('preserve',encoding='utf-8')
            try:(self.root/'logs/errors.jsonl').symlink_to(target)
            except OSError:self.skipTest('Symlink creation unavailable on this Windows account')
            with contextlib.redirect_stderr(io.StringIO()):self.assertFalse(self.save(E('E_UNKNOWN')))
            self.assertEqual(target.read_text(encoding='utf-8'),'preserve')

if __name__=='__main__':unittest.main()
