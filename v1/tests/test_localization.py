import tempfile
import shutil
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

from PySide6.QtCore import QLocale,QSettings,Qt,QTranslator
from PySide6.QtWidgets import QApplication
from depthsbs_app.desktop import DesktopController
from depthsbs_app.desktop_preferences import DesktopPreferences
from depthsbs_app.live_preview import LivePreview
from depthsbs_app.localization import LanguageManager,render,resolve_language
from depthsbs_app.messages import Message as M


class LocalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.old_locale=QLocale()
        self.prefs=DesktopPreferences(QSettings(self.temp.name+'/preferences.ini',QSettings.IniFormat))
        self.prefs.store.setValue('ui/language','ko')
        self.desktop=DesktopController(self.prefs)
        with patch('depthsbs_app.live_preview.windows',return_value=[]):
            self.live=LivePreview(self.desktop)
        self.desktop.live=self.live
        self.language=LanguageManager(self.prefs,self.desktop)
        self.language.engine=Mock()
        self.language.refresh=Mock()

    def tearDown(self):
        self.live.process=None
        self.language.close()
        QLocale.setDefault(self.old_locale)
        self.desktop.deleteLater()

    def test_system_and_unsupported_language_fallback(self):
        for locale,expected in (('ko_KR','ko'),('en_GB','en'),('de_DE','en')):
            self.assertEqual(resolve_language('system',QLocale(locale)),expected)
        self.assertEqual(resolve_language('en',QLocale('ko_KR')),'en')
        self.assertEqual(resolve_language('ko',QLocale('en_US')),'ko')

    def test_translates_dynamic_stored_messages_and_keeps_external_titles(self):
        self.live.message=M('Added: {v0} · Select a file to convert.',v0=3)
        self.assertIn('3개',self.live.status)
        self.live.items=[dict(kind='window',id=123,pid=45,label='닫기 / Close')]
        self.language.setLanguage('en')
        self.assertIn('Added: 3',self.live.status)
        self.assertEqual(self.live.sources[0]['label'],'닫기 / Close')
        self.language.setLanguage('ko')
        self.assertIn('3개',self.live.status)
        self.language.engine.retranslate.assert_called()

    def test_completed_file_and_live_identity_survive_busy_language_switch(self):
        output=Path(self.temp.name)/'한글 output.mp4';output.touch()
        self.desktop.rows=[dict(name='한글.mp4',source='opaque',output=str(output),state='completed')]
        self.desktop.selected=0
        self.desktop.lease.acquire('live')
        process=Mock();self.live.process=process
        source=dict(kind='window',id=123,pid=45,label='게임')
        self.live.source=source;self.live.session=17;self.live.vfg_enabled=True
        before=(self.live.session,self.live.mode,self.live.live_model,self.live.stereo_layout,self.live.version)
        for language,label in (('en','Completed'),('ko','완료')):
            self.language.setLanguage(language)
            self.assertEqual(self.desktop.jobs[0]['stateLabel'],label)
            self.assertEqual(self.desktop.rows[0]['state'],'completed')
            self.assertTrue(self.desktop.canOpen)
            self.assertIs(self.live.process,process)
            self.assertIs(self.live.source,source)
            self.assertTrue(self.live.vfg_enabled)
            self.assertEqual(before,(self.live.session,self.live.mode,self.live.live_model,self.live.stereo_layout,self.live.version))
            process.assert_not_called()

    def test_saves_valid_language_and_preserves_existing_selections(self):
        self.prefs.remember('live','balanced','da2-base','half-sbs')
        self.language.setLanguage('en')
        store=QSettings(self.temp.name+'/preferences.ini',QSettings.IniFormat)
        self.assertEqual(store.value('ui/language'),'en')
        self.assertEqual(store.value('live/model'),'da2-base')
        self.language.setLanguage('invalid')
        self.assertEqual(self.language.selected,'en')

    def test_installer_and_precision_retranslate_without_restarting(self):
        downloads=self.desktop.downloads
        downloads.message=M('Downloading files');downloads.active_key='da2-base';downloads.percent=43
        self.assertEqual(downloads.status,'파일 받는 중')
        self.language.setLanguage('en')
        self.assertEqual(downloads.status,'Downloading files')
        self.assertEqual((downloads.active_key,downloads.percent),('da2-base',43))
        self.assertFalse(downloads.stop_event.is_set())
        self.assertIn('Mixed FP16',self.desktop.depthChoices[1]['label'])
        self.language.setLanguage('ko')
        self.assertIn('FP16 혼합',self.desktop.depthChoices[1]['label'])

    def test_missing_catalog_falls_back_to_english(self):
        with patch('depthsbs_app.localization.QTranslator.load',return_value=False):
            self.language._apply()
        self.assertEqual(self.language.effectiveLanguage,'en')
        self.assertEqual(render(M('Close')),'Close')

    def test_system_number_format_does_not_change_machine_messages(self):
        value=M('Value: {value:.1f}',value=1234.5)
        with patch('depthsbs_app.localization.QLocale.system',return_value=QLocale('de_DE')):
            self.language.setLanguage('system')
            self.assertEqual(self.language.effectiveLanguage,'en')
            self.assertEqual(self.language.localeName,'de_DE')
            self.assertIn('1.234,5',render(value))
            self.assertEqual(str(value),'Value: 1234.5')
            self.language.engine.setUiLanguage.assert_called_with('en-US')

    def test_setting_failure_keeps_the_active_language(self):
        errors=[];self.language.errorOccurred.connect(errors.append)
        with patch.object(self.prefs.store,'status',return_value=QSettings.AccessError):
            self.language.setLanguage('en')
        self.assertEqual(self.language.selected,'ko')
        self.assertEqual(self.language.effectiveLanguage,'ko')
        self.assertEqual(len(errors),1)
        self.language.engine.retranslate.assert_not_called()

    def test_unsupported_rtl_system_uses_english_without_mirroring(self):
        with patch('depthsbs_app.localization.QLocale.system',return_value=QLocale('ar_EG')):
            self.language.setLanguage('system')
            self.assertEqual(self.language.effectiveLanguage,'en')
            self.assertEqual(self.language.localeName,'en_US')
            self.assertEqual(self.app.layoutDirection(),Qt.LeftToRight)

    def test_bundled_catalog_loads_from_non_ascii_path(self):
        from depthsbs_app import localization
        folder=Path(self.temp.name)/'한글 경로 with spaces';folder.mkdir()
        target=folder/'screento3d_ko.qm'
        shutil.copyfile(Path(localization.__file__).with_name('translations')/'screento3d_ko.qm',target)
        translator=QTranslator()
        self.assertTrue(translator.load(str(target)))
        self.assertEqual(translator.translate('ScreenTo3D','Close'),'닫기')

    def test_hidden_error_is_not_replaced_by_stop_completion(self):
        self.desktop.error_dialog=SimpleNamespace(showError=lambda message:False)
        self.live.stop=Mock(side_effect=lambda:setattr(self.live,'stop_message_pending',True))
        self.desktop.showLiveError(M('The selected window closed. Select another window.'))
        self.assertFalse(self.live.stop_message_pending)
        self.language.setLanguage('en')
        self.assertIn('selected window closed',self.live.status)
        self.assertIn('capture protection failed',self.live.status)
