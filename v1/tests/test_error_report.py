"""Regression checks for the boundary between local logs and user-shared reports."""
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from threading import Event
from time import monotonic
from unittest.mock import patch

from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from screento3d_app.error_dialog import LiveErrorDialog
from screento3d_app.error_journal import read_recent_reports
from screento3d_app.error_report import prepare_report, report_text
from screento3d_app.error_report_dialog import ErrorReportDialog
from screento3d_app.messages import ErrorMessage
from screento3d_app.report_pc import collect_pc_info


PC_INFO = {
    "windows": "10.0.26100 (AMD64)", "cpu": "Test Processor", "memory_gib": 16,
    "gpu": [("Intel(R) Arc(TM) Graphics", "32.0.101.1234")],
}


def error_record(second):
    secret = r'C:\Users\PRIVATE_NAME\Desktop\PRIVATE_MEDIA.mp4'
    return {
        'schema': 1, 'timestamp': f'2026-11-18T16:03:{second:02d}+09:00',
        'app_version': '1.0.0', 'error_id': 'E_CAPTURE_STOPPED', 'activity': 'live',
        'details': secret, 'message': secret, 'launch_log': secret,
        'diagnostics': {
            'qpc_ns': 2_000_000_000,
            'context': {
                'identity': {'executable': secret, 'app_root': secret, 'run_id': secret},
                'settings': {'model': 'da2-small', 'layout': 'half-tb', 'limit_hz': 60, 'vfg': False,
                             'source': {'title': secret, 'id': 6006, 'pid': 56789}},
                'worker': {'failure': {'traceback': secret}},
            },
            'samples': [{
                'qpc_ns': 1_000_000_000, 'state': {
                    'source': {'title': secret, 'client_px': [1920, 1080]},
                    'processing': {'frames': 14},
                },
            }],
            'events': [
                {'qpc_ns': 1_990_000_000, 'name': 'worker_exit', 'data': {'exit_code': -15, 'worker_pid': 56789}},
                {'qpc_ns': 1_500_000_000, 'name': secret, 'data': {'fullscreen': True}},
            ],
        },
    }


class ErrorReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.logs = self.root / 'logs'
        self.logs.mkdir()
        self.enterContext(patch('screento3d_app.user_data.data_root', return_value=self.root))
        self.enterContext(patch('screento3d_app.capture_sources.exclude_preview', return_value=True))
        self.enterContext(patch('screento3d_app.error_report_dialog.collect_pc_info', return_value=PC_INFO))

    def wait_for_pc_info(self, dialog):
        deadline = monotonic() + 2
        while 'Collecting PC information' in dialog.preview.toPlainText() and monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(dialog.save_button.isEnabled())

    def test_gpu_collection_includes_intel_and_filters_private_fields(self):
        values = {
            'gpu': [
                {'Name': 'Intel(R) Arc(TM) Graphics', 'DriverVersion': '32.0.101.1234',
                 'DeviceID': 'PRIVATE_ID'},
                {'Name': 'PRIVATE\\PATH', 'DriverVersion': '32.0.0.0'},
                {'Name': 'Driver pending', 'DriverVersion': 'PRIVATE_DRIVER_PATH'},
            ],
            'cpu': 'Test Processor', 'memory': 16 * 2**30,
            'pc_name': 'PRIVATE_HOST', 'user': 'PRIVATE_USER',
        }
        with patch('screento3d_app.report_pc.subprocess.run',
                   return_value=SimpleNamespace(stdout=json.dumps(values))) as query:
            info = collect_pc_info()
        self.assertEqual(query.call_args.kwargs['timeout'], 5)
        self.assertEqual(info['gpu'], [('Intel(R) Arc(TM) Graphics', '32.0.101.1234'), ('Driver pending', '')])
        shared = report_text(prepare_report(error_record(1)), str, pc_info=info)
        self.assertIn('Physical memory: 16.0 GiB', shared)
        self.assertIn('Graphics driver: 32.0.101.1234', shared)
        self.assertNotIn('PRIVATE_', shared)

    def test_save_with_pc_info_disabled_does_not_wait_for_query(self):
        release = Event()
        self.addCleanup(release.set)
        owner = QQuickWindow()
        dialog = ErrorReportDialog()
        self.addCleanup(owner.deleteLater)
        self.addCleanup(dialog.deleteLater)
        self.addCleanup(dialog.close)

        def collect():
            release.wait(2)
            return PC_INFO

        with patch('screento3d_app.error_report_dialog.collect_pc_info', side_effect=collect):
            self.assertTrue(dialog.open_report(owner, prepare_report(error_record(1))))
            self.assertIn('Collecting PC information', dialog.preview.toPlainText())
            self.assertFalse(dialog.save_button.isEnabled())
            dialog.include_pc.setChecked(False)
            self.assertTrue(dialog.save_button.isEnabled())
            self.assertNotIn('PC information', dialog.preview.toPlainText())
            self.assertNotIn('Arc', dialog.preview.toPlainText())
            dialog.include_pc.setChecked(True)
            release.set()
            self.wait_for_pc_info(dialog)
            self.assertIn('Intel(R) Arc(TM) Graphics', dialog.preview.toPlainText())

    def test_public_text_excludes_paths_ids_and_raw_events_by_construction(self):
        entry = prepare_report(error_record(1))
        basic = report_text(entry, str)
        self.assertIn('da2-small', basic)
        self.assertIn('Worker exit code: -15', basic)
        self.assertNotIn('1920×1080', basic)
        expanded = report_text(entry, str, include_diagnostics=True)
        self.assertIn('1920×1080', expanded)
        self.assertIn('worker_exit', expanded)
        for text in (basic, expanded):
            for secret in ('PRIVATE_', '56789', '6006'):
                self.assertNotIn(secret, text)

    def test_history_preserves_repeated_ids_and_resumes_after_malformed_lines(self):
        old = error_record(1)
        old.pop('activity')  # Older schema 1 records are still usable.
        (self.logs / 'errors.1.jsonl').write_text(json.dumps(old)+'\n', encoding='utf-8')
        file = self.logs / 'errors.jsonl'
        current = json.dumps(error_record(2))+'\n{partial line\n'
        file.write_text(current, encoding='utf-8')
        reports, partial = read_recent_reports()
        self.assertTrue(partial)
        self.assertEqual([entry['time'].second for entry in reports], [2, 1])
        self.assertEqual([entry['activity'] for entry in reports], ['live', 'live'])
        self.assertEqual(file.read_text(encoding='utf-8'), current)

    def test_report_remains_available_while_journal_write_fails(self):
        owner = QQuickWindow()
        dialog = LiveErrorDialog(owner)
        self.addCleanup(owner.deleteLater)
        self.addCleanup(dialog.deleteLater)
        self.addCleanup(dialog.close)
        with patch('screento3d_app.error_dialog.record_error', return_value=False):
            dialog.showError(ErrorMessage('E_CAPTURE_SOURCE_CLOSED', details='PRIVATE_DIAGNOSTIC'))
        dialog.report_button.click()
        report = dialog.report_dialog()
        self.addCleanup(report.close)
        self.assertTrue(report.isVisible())
        self.wait_for_pc_info(report)
        self.assertIn('E_CAPTURE_SOURCE_CLOSED', report.preview.toPlainText())
        self.assertNotIn('PRIVATE_DIAGNOSTIC', report.preview.toPlainText())

    def test_history_selection_preview_and_saved_file_match(self):
        journal = self.logs / 'errors.jsonl'
        journal.write_text('\n'.join(json.dumps(error_record(i)) for i in (1, 2)), encoding='utf-8')
        owner = QQuickWindow()
        dialog = ErrorReportDialog()
        self.addCleanup(owner.deleteLater)
        self.addCleanup(dialog.deleteLater)
        self.addCleanup(dialog.close)
        self.assertTrue(dialog.open_history(owner))
        self.assertEqual(dialog.history.count(), 2)
        self.wait_for_pc_info(dialog)
        dialog.note.setText('Note for the second occurrence')
        dialog.diagnostics.setChecked(True)
        dialog.history.setCurrentRow(1)
        self.assertFalse(dialog.diagnostics.isChecked())
        self.assertEqual(dialog.note.text(), '')
        dialog.note.setText('Veyra에서 메뉴 열기')
        dialog.diagnostics.setChecked(True)
        preview = dialog.preview.toPlainText()
        self.assertIn('16:03:01', preview)
        self.assertIn('1920×1080', preview)
        self.assertIn('Veyra에서 메뉴 열기', preview)
        self.assertIn('Intel(R) Arc(TM) Graphics', preview)
        self.assertIn('32.0.101.1234', preview)
        self.assertNotIn('16:03:02', preview)
        with patch('screento3d_app.error_report_dialog.QFileDialog.getSaveFileName', return_value=('', '')):
            dialog.save_button.click()
        self.assertFalse(dialog.saved)
        target = self.root / 'report'
        with patch('screento3d_app.error_report_dialog.QFileDialog.getSaveFileName',
                   return_value=(str(target), '')):
            dialog.save_button.click()
        self.assertTrue(dialog.saved)
        self.assertEqual(target.with_suffix('.txt').read_text(encoding='utf-8'), preview)
        before = journal.read_bytes()
        with patch('screento3d_app.error_report_dialog.QFileDialog.getSaveFileName',
                   return_value=(str(journal), '')):
            dialog.save_button.click()
        self.assertTrue(dialog.save_failed)
        self.assertEqual(journal.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
