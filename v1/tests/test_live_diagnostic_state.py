"""Failed/cleaned live resources must not erase or block error diagnostics."""
import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from PySide6.QtCore import QSettings,Qt
from PySide6.QtWidgets import QApplication
from screento3d_app.desktop import DesktopController
from screento3d_app.desktop_preferences import DesktopPreferences
from screento3d_app.live_preview import LivePreview
from screento3d_app.messages import ErrorMessage as E
from screento3d_app.live_sbs import STAT_COUNT
from screento3d_app.error_dialog import LiveErrorDialog
from PySide6.QtQuick import QQuickWindow

class LiveDiagnosticStateTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.desktop=DesktopController(DesktopPreferences(QSettings(self.tmp.name+'/prefs.ini',QSettings.IniFormat)))
  with patch('screento3d_app.live_preview.windows',return_value=[]):self.live=LivePreview(self.desktop)
  self.desktop.live=self.live;self.addCleanup(self.live.diagnostics.timer.stop)
  self.live.source=dict(kind='window',id=123,pid=9,label='PRIVATE WINDOW TITLE',width=1920,height=1080)
  self.live.process=SimpleNamespace(pid=9);self.live.session=1
  self.live.processing_stats=[0]*STAT_COUNT;self.live.processing_stats[0]=42
  self.live.native=SimpleNamespace(report=lambda:dict(output=dict(submitted_frames=41),live_pools=1,live_nodes=1))
  self.enterContext(patch.object(self.live.diagnostics,'source_state',return_value=dict(valid=True,visible=True,minimized=False,client_px=[1920,1080])))
  self.live.diagnostics.begin()
 def tearDown(self):
  self.live.process=None;self.live.diagnostics.timer.stop();self.desktop.deleteLater();self.app.processEvents()
 def test_abort_freezes_before_stop_clears_resources(self):
  def stop():self.live.process=None;self.live.native=None;self.live.processing_stats[0]=0
  with patch.object(self.live,'stop',side_effect=stop):self.live.abort(E('E_OUTPUT_DISPLAY_CHANGED'))
  saved=self.live.diagnostics.take_error(self.live.message)
  self.assertEqual(saved['context']['trigger'],'before_abort_cleanup')
  row=saved['samples'][-1]['state'];self.assertTrue(row['active']);self.assertEqual(row['processing']['frames'],42);self.assertEqual(row['output']['pools'],1)
  self.assertNotIn('PRIVATE WINDOW TITLE',json.dumps(saved))

 def test_display_notification_aborts_and_freezes_before_cleanup(self):
  window=Mock()
  window.isVisible.return_value=True
  self.live.output_window=window

  def stop():
   self.live.process=None
   self.live.native=None

  with patch.object(self.live,'stop',side_effect=stop):
   self.live.screensChanged()

  self.assertEqual(self.live.message.error_id,'E_OUTPUT_DISPLAY_CHANGED')
  saved=self.live.diagnostics.take_error(self.live.message)
  self.assertEqual(saved['samples'][-1]['state']['output']['pools'],1)
  self.assertIn('displays_changed',[event['name'] for event in saved['events']])
  window.hide.assert_called_once()

 def test_failed_native_probe_keeps_other_state_and_original_error(self):
  self.live.native=SimpleNamespace(report=Mock(side_effect=RuntimeError('failed device')))
  self.live.diagnostics.freeze('failed_device');saved=self.live.diagnostics.take_error(E('E_UNKNOWN'))
  self.assertEqual(saved['samples'][-1]['state']['processing']['frames'],42)
  self.assertGreater(saved['context']['sampling_failures'],0)
 def test_failed_sampler_does_not_raise_or_hide_next_report(self):
  with patch.object(self.live.diagnostics,'state',side_effect=RuntimeError('probe failed')):
   self.live.diagnostics.sample();self.live.diagnostics.freeze('probe_failed')
  self.assertIsNotNone(self.live.diagnostics.take_error(E('E_UNKNOWN')))
 def test_sampling_and_transitions_do_not_write_files(self):
  self.live.diagnostics.build_identity()
  with patch('builtins.open',side_effect=AssertionError('success path wrote a file')):
   self.live.diagnostics.sample();self.live.diagnostics.note('fullscreen_requested',was_fullscreen=False)
  self.assertEqual(self.live.diagnostics.flight.events[-1]['name'],'fullscreen_requested')
 def test_dialog_persists_context_once_even_if_window_protection_fails(self):
  owner=QQuickWindow();dialog=LiveErrorDialog(owner)
  try:
   self.live.diagnostics.freeze('test_error');dialog.diagnostic_context=self.live.diagnostics.take_error(E('E_UNKNOWN'))
   with patch('screento3d_app.user_data.data_root',return_value=Path(self.tmp.name)/'data'),patch('screento3d_app.capture_sources.exclude_preview',return_value=False):
    self.assertFalse(dialog.showError(E('E_UNKNOWN')));dialog.retranslate()
   entry=json.loads((Path(self.tmp.name)/'data/logs/errors.jsonl').read_text(encoding='utf-8'))
   self.assertEqual(entry['diagnostics']['context']['trigger'],'test_error')
   self.assertEqual(entry['diagnostics']['samples'][-1]['state']['output']['submitted'],41)
   self.assertIsNone(dialog.diagnostic_context)
  finally:dialog.close();dialog.deleteLater();owner.deleteLater();self.app.processEvents()
 def test_idle_sampling_timer_stops_and_vfg_restart_retains_history(self):
  self.assertEqual(self.live.diagnostics.timer.timerType(),Qt.PreciseTimer)
  self.assertEqual(self.live.diagnostics.timer.interval(),1000)
  self.live.diagnostics.sample();count=len(self.live.diagnostics.flight.samples)
  self.live.diagnostics.begin(restart=True);self.assertEqual(len(self.live.diagnostics.flight.samples),count)
  self.live.process=None;self.live.diagnostics.sync();self.assertFalse(self.live.diagnostics.timer.isActive())
  self.live.diagnostics.begin();self.assertEqual(len(self.live.diagnostics.flight.samples),0)

if __name__=='__main__':unittest.main()
