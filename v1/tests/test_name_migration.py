import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch

from PySide6.QtCore import QSettings
from screento3d_app.environment import get,required


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

    def test_default_settings_use_only_explicit_ini_and_survive_reopen(self):
        from screento3d_app.desktop_preferences import DesktopPreferences
        from screento3d_app import user_data
        with tempfile.TemporaryDirectory() as folder,patch.object(user_data,'APP_ROOT',Path(folder)):
            current=DesktopPreferences()
            self.assertEqual(current.store.format(),QSettings.IniFormat)
            self.assertEqual(Path(current.store.fileName()),Path(folder)/'data/settings.ini')
            current.remember('live','balanced','da2-base','half-sbs')
            current.store.setValue('ui/language','ko');current.store.setValue('SbsOutput/fullscreenStats',True);current.store.sync()
            reopened=DesktopPreferences()
            self.assertEqual(reopened.selection('live',{'balanced','performance'}),
                             dict(mode='balanced',model='da2-base',stereo_layout='half-sbs'))
            self.assertEqual(reopened.store.value('ui/language'),'ko')

    def test_malformed_ini_fails_with_stable_error_instead_of_resetting(self):
        from screento3d_app.desktop_preferences import DesktopPreferences
        from screento3d_app import user_data
        with tempfile.TemporaryDirectory() as folder,patch.object(user_data,'APP_ROOT',Path(folder)):
            path=user_data.settings_file();path.parent.mkdir();path.write_text('[broken\nvalue=1\n')
            with self.assertRaises(OSError) as result:DesktopPreferences()
            self.assertEqual(result.exception.args[0].error_id,'E_SETTINGS_FILE_INVALID')
            self.assertEqual(path.read_text(),'[broken\nvalue=1\n')

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
