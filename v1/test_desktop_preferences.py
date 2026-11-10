"""Selection persistence uses temporary INI files, never the user's registry."""
import tempfile
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from depthsbs_app.config import MODES
from depthsbs_app.desktop import DesktopController
from depthsbs_app.desktop_preferences import DesktopPreferences
from depthsbs_app.live_policy import LIVE_MODES
from depthsbs_app.live_preview import LivePreview

APP = QApplication.instance() or QApplication([])


class PreferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = self.temp.name + '/settings.ini'
        self.prefs = DesktopPreferences(QSettings(self.path, QSettings.IniFormat))

    def controllers(self, prefs=None):
        desktop = DesktopController(prefs if prefs is not None else self.prefs)
        desktop.live = LivePreview(desktop)
        return desktop, desktop.live

    def test_fresh_source_uses_small_half_tb_even_with_base_installed(self):
        desktop, live = self.controllers()
        self.assertEqual((live.liveMode, live.liveModel, live.stereoLayout), ('performance', 'da2-small', 'half-tb'))
        self.assertEqual((desktop.settings['mode'], desktop.settings['model'], desktop.settings['stereo_layout']),
                         ('performance', 'da2-small', 'half-tb'))

    def test_user_choices_survive_new_store_and_controller_independently(self):
        desktop, live = self.controllers()
        live.setMode('balanced')
        live.setStereoLayout('half-sbs')
        live.rememberSelection()
        desktop.setOption('mode', 'offline-quality')
        desktop.setOption('stereo_layout', 'full-tb')
        desktop.rememberSelection()
        fresh = DesktopPreferences(QSettings(self.path, QSettings.IniFormat))
        reopened, restored = self.controllers(fresh)
        self.assertEqual((restored.liveMode, restored.liveModel, restored.stereoLayout), ('balanced', 'da2-base', 'half-sbs'))
        self.assertEqual((reopened.settings['mode'], reopened.settings['model'], reopened.settings['stereo_layout']),
                         ('offline-quality', 'vda-small', 'full-tb'))
        self.assertEqual(set(fresh.store.allKeys()), {'live/mode', 'live/model', 'live/stereoLayout',
                                                    'file/mode', 'file/model', 'file/stereoLayout'})
        self.assertFalse(restored.ovdaConfirmed)
        self.assertFalse(restored.vfgEnabled)

    def test_programmatic_overrides_and_comparison_do_not_write_choices(self):
        desktop, live = self.controllers()
        live.setMode('balanced')
        live.setStereoLayout('full-sbs')
        desktop.setOption('mode', 'video-quality')
        self.assertEqual(self.prefs.store.allKeys(), [])
        live.vfg_configurable = False
        live.rememberSelection()
        self.assertEqual(self.prefs.store.allKeys(), [])

    def test_busy_or_running_session_does_not_save(self):
        desktop, live = self.controllers()
        desktop.lease.acquire('file')
        live.rememberSelection()
        desktop.rememberSelection()
        desktop.lease.release('file')
        live.process = object()
        live.rememberSelection()
        live.process = None
        self.assertEqual(self.prefs.store.allKeys(), [])

    def test_corrupt_values_and_offline_live_mode_reset_to_valid_defaults(self):
        for name, value in (('mode', 'offline-quality'), ('model', ['unexpected']), ('stereoLayout', 'unknown')):
            self.prefs.store.setValue('live/' + name, value)
        self.assertEqual(self.prefs.selection('live', LIVE_MODES),
                         dict(mode='performance', model='da2-small', stereo_layout='half-tb'))
        self.prefs.store.setValue('file/mode', 12)
        self.assertEqual(self.prefs.selection('file', MODES)['mode'], 'performance')

    def test_selected_video_model_is_kept_without_restoring_consent(self):
        self.prefs.remember('live', 'video-quality', 'ovda-small-c16', 'half-tb')
        desktop, live = self.controllers()
        self.assertEqual(live.liveModel, 'ovda-small-c16')
        self.assertFalse(live.ovdaConfirmed)
        portable = DesktopPreferences(self.prefs.store, portable=True)
        self.assertEqual(portable.selection('live', LIVE_MODES)['model'], 'vda-small')

    def test_write_error_is_reported(self):
        store = Mock()
        store.status.return_value = QSettings.AccessError
        with self.assertRaises(OSError):
            DesktopPreferences(store).remember('live', 'performance', 'da2-small', 'half-tb')

    def test_model_choices_keep_routing_and_saved_selection(self):
        desktop, live = self.controllers()
        for choice in live.depthChoices:
            live.selectDepthModel(choice['key'])
            self.assertEqual((live.liveMode, live.liveModel), (choice['mode'], choice['model']))
        live.selectDepthModel('video-quality/vda-small')
        live.rememberSelection()
        desktop.selectDepthModel('offline-quality/vda-small')
        desktop.rememberSelection()
        reopened, restored = self.controllers()
        self.assertEqual((restored.liveMode, restored.liveModel), ('video-quality', 'vda-small'))
        self.assertEqual(reopened.settings['mode'], 'offline-quality')
        live.selectDepthModel('offline-quality/vda-small')
        live.selectDepthModel('invalid')
        self.assertEqual(live.liveMode, 'video-quality')
        desktop.lease.acquire('file')
        live.selectDepthModel('balanced/da2-base')
        desktop.selectDepthModel('performance/da2-small')
        self.assertEqual(live.liveMode, 'video-quality')
        self.assertEqual(desktop.settings['mode'], 'offline-quality')

    def test_vda_precision_distinguishes_installed_legacy_and_download_target(self):
        from depthsbs_app.model_presentation import model_info
        with patch('depthsbs_app.model_presentation.available', return_value=True), patch(
            'depthsbs_app.vda_artifacts.uses_mixed_fp16', return_value=False
        ):
            self.assertEqual(model_info('vda-small', 'legacy')[1], 'FP32')
        with patch('depthsbs_app.model_presentation.available', return_value=True), patch(
            'depthsbs_app.vda_artifacts.uses_mixed_fp16', return_value=True
        ):
            name, precision, help_text = model_info('vda-small', 'managed')
            self.assertEqual(precision, 'FP16 혼합')
            self.assertIn('시간축 처리·이력과 입출력은 FP32', help_text)
        with patch('depthsbs_app.model_presentation.available', return_value=False):
            self.assertIn('미설치', model_info('vda-small', '')[2])

    def test_portable_model_choices_and_order(self):
        from depthsbs_app.model_presentation import selection_choices
        choices = selection_choices(LIVE_MODES, {}, portable=True)
        self.assertEqual([c['model'] for c in choices], ['da2-small', 'da2-base', 'vda-small'])
        self.assertEqual(len({c['key'] for c in choices}), len(choices))
        self.assertTrue(choices[0]['label'].endswith('기본'))
        offline = selection_choices(MODES, {}, portable=True)[-1]
        self.assertEqual(offline['mode'], 'offline-quality')
        self.assertIn('5프레임', offline['label'])
        self.assertNotIn('VFG', offline['help'])


if __name__ == '__main__':
    unittest.main()
