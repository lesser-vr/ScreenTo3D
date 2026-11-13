import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch

from PySide6.QtCore import QSettings
from screento3d_app.environment import get,required
from screento3d_app.desktop_preferences import migrate_settings


class NameMigrationTests(unittest.TestCase):
    def test_legacy_environment_is_read_dynamically_without_mutation(self):
        with patch.dict(os.environ,{'DEPTHSBS_BASE_INPUT':'cpu'},clear=True):
            self.assertEqual(get('SCREENTO3D_BASE_INPUT'),'cpu')
            self.assertNotIn('SCREENTO3D_BASE_INPUT',os.environ)
            os.environ['DEPTHSBS_BASE_INPUT']='gpu'
            self.assertEqual(get('SCREENTO3D_BASE_INPUT'),'gpu')

    def test_new_environment_wins_including_empty_values(self):
        with patch.dict(os.environ,{'DEPTHSBS_BASE_INPUT':'cpu','STEREOTO3D_BASE_INPUT':'gpu','SCREENTO3D_BASE_INPUT':''},clear=True):
            self.assertEqual(get('SCREENTO3D_BASE_INPUT'),'')
            self.assertEqual(required('SCREENTO3D_BASE_INPUT'),'')

    def test_interim_environment_precedes_original_legacy(self):
        with patch.dict(os.environ,{'DEPTHSBS_BASE_INPUT':'cpu','STEREOTO3D_BASE_INPUT':'gpu'},clear=True):
            self.assertEqual(get('SCREENTO3D_BASE_INPUT'),'gpu')

    def test_environment_defaults_and_required_errors_are_truthful(self):
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(get('SCREENTO3D_BASE_INPUT','gpu'),'gpu')
            with self.assertRaises(KeyError):required('SCREENTO3D_LAUNCH_LOG')

    def test_launcher_compatibility_uses_the_canonical_implementation(self):
        from depthsbs_app.launcher import main as old
        from screento3d_app.launcher import main as current
        self.assertIs(old,current)
        from stereoto3d_app.launcher import main as interim
        self.assertIs(interim,current)
        from depthsbs_app.main import main as old_cli
        from screento3d_app.main import main as current_cli
        self.assertIs(old_cli,current_cli)
        from depthsbs_app.desktop import main as old_desktop
        from screento3d_app.desktop import main as current_desktop
        self.assertIs(old_desktop,current_desktop)

    def stores(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        return tuple(QSettings(str(Path(folder.name)/name),QSettings.IniFormat) for name in ('new.ini','old.ini'))

    def test_settings_adopt_owned_values_and_retain_the_legacy_store(self):
        current,legacy=self.stores()
        values={'ui/language':'ko','live/model':'da2-base','live/mode':'balanced',
                'live/stereoLayout':'half-sbs','file/mode':'video-quality','file/model':'vda-small','file/stereoLayout':'sbs'}
        for key,value in values.items():legacy.setValue(key,value)
        legacy.setValue('unowned/privatePath','not migrated')
        migrate_settings(current,legacy)
        for key,value in values.items():
            self.assertEqual(current.value(key),value);self.assertEqual(legacy.value(key),value)
        self.assertFalse(current.contains('unowned/privatePath'))
        migrate_settings(current,legacy)

    def test_settings_never_override_new_values_on_repeated_migration(self):
        current,legacy=self.stores();legacy.setValue('ui/language','ko');current.setValue('ui/language','system')
        migrate_settings(current,legacy);legacy.setValue('ui/language','en');migrate_settings(current,legacy)
        self.assertEqual(current.value('ui/language'),'system')

    def test_settings_adopt_interim_before_original_without_overwriting_current(self):
        current,interim=self.stores()
        legacy=QSettings(current.fileName()+'.legacy',QSettings.IniFormat)
        current.setValue('ui/language','en');interim.setValue('ui/language','ko')
        interim.setValue('live/model','da2-base');legacy.setValue('live/model','da2-small')
        legacy.setValue('file/model','vda-small')
        migrate_settings(current,interim,legacy)
        self.assertEqual(current.value('ui/language'),'en')
        self.assertEqual(current.value('live/model'),'da2-base')
        self.assertEqual(current.value('file/model'),'vda-small')

    def test_unreadable_settings_stop_before_mutation_with_an_error_id(self):
        current,legacy=self.stores();legacy.setValue('ui/language','ko')
        with patch.object(current,'status',return_value=QSettings.AccessError):
            with self.assertRaises(OSError) as result:migrate_settings(current,legacy)
        self.assertEqual(result.exception.args[0].error_id,'E_SETTINGS_MIGRATION')
        self.assertFalse(current.contains('ui/language'));self.assertEqual(legacy.value('ui/language'),'ko')

    def test_outputs_from_both_versions_are_recognized(self):
        from screento3d_app import capture_sources as sources
        for marker in (sources.SBS_OUTPUT_PROPERTY,sources.INTERIM_OUTPUT_PROPERTY,sources.LEGACY_OUTPUT_PROPERTY):
            api=Mock();api.GetPropW.side_effect=lambda hwnd,name:name==marker
            with patch.object(sources,'user32',api):self.assertTrue(sources.is_sbs_output(123))

    def test_new_output_is_marked_for_both_versions(self):
        from screento3d_app import capture_sources as sources
        api=Mock();api.SetPropW.return_value=1
        api.GetWindowThreadProcessId.side_effect=lambda hwnd,pid:setattr(pid._obj,'value',os.getpid())
        with patch.object(sources,'user32',api):self.assertTrue(sources.mark_sbs_output(123))
        self.assertEqual([call.args[1] for call in api.SetPropW.call_args_list],
                         [sources.SBS_OUTPUT_PROPERTY,sources.INTERIM_OUTPUT_PROPERTY,sources.LEGACY_OUTPUT_PROPERTY])

    def test_foreign_window_is_never_marked(self):
        from screento3d_app import capture_sources as sources
        api=Mock();api.GetWindowThreadProcessId.side_effect=lambda hwnd,pid:setattr(pid._obj,'value',os.getpid()+1)
        with patch.object(sources,'user32',api):self.assertFalse(sources.mark_sbs_output(123))
        api.SetPropW.assert_not_called()


if __name__=='__main__':unittest.main()
