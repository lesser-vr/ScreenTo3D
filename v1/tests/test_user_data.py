import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from screento3d_app import user_data as paths


class UserDataTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.base=Path(folder.name);self.app=self.base/'app';self.app.mkdir();self.local=self.base/'old-local'
        self.enterContext(patch.object(paths,'APP_ROOT',self.app))
        self.enterContext(patch.dict(os.environ,{'LOCALAPPDATA':str(self.local)}))
        self.enterContext(patch.object(tempfile,'tempdir',tempfile.tempdir))
        self.enterContext(patch.object(sys,'dont_write_bytecode',sys.dont_write_bytecode))

    def test_path_discovery_is_app_relative_and_has_no_side_effect(self):
        self.assertEqual(paths.data_root(),self.app/'data')
        self.assertEqual(paths.settings_file(),self.app/'data/settings.ini')
        self.assertFalse(paths.data_root().exists());self.assertFalse(self.local.exists())

    def test_frozen_entry_uses_executable_folder_instead_of_internal_resources(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('screento3d_app._frozen_paths',paths.__file__)
        module=importlib.util.module_from_spec(spec)
        with patch.object(sys,'frozen',True,create=True),patch.object(sys,'executable',str(self.app/'ScreenTo3D.exe')):
            spec.loader.exec_module(module)
        self.assertEqual(module.data_root(),self.app.resolve()/'data')

    def test_preparation_redirects_caches_and_temp_without_automatic_import(self):
        source=self.local/'ScreenTo3D/models/old.plan';source.parent.mkdir(parents=True);source.write_bytes(b'owned source')
        root=paths.prepare_environment()
        self.assertTrue((root/'temp').is_dir());self.assertEqual(tempfile.gettempdir(),str(root/'temp'))
        self.assertEqual(os.environ['QML_DISK_CACHE_PATH'],str(root/'cache/qml'))
        self.assertEqual(os.environ['QSG_RHI_PIPELINE_CACHE_SAVE'],str(root/'cache/qt/pipeline.cache'))
        self.assertEqual(os.environ['CUDA_CACHE_PATH'],str(root/'cache/cuda'))
        self.assertTrue(source.is_file());self.assertFalse((root/'models/old.plan').exists())

    def test_permission_failure_never_falls_back_to_appdata(self):
        with patch.object(tempfile,'TemporaryFile',side_effect=PermissionError('private path')):
            with self.assertRaises(OSError) as result:paths.prepare_environment()
        self.assertEqual(result.exception.args[0].error_id,'E_PORTABLE_WRITE')
        self.assertFalse(self.local.exists());self.assertNotIn('private path',str(result.exception))

    def test_linked_data_root_is_rejected(self):
        with patch.object(Path,'is_symlink',lambda path:path==self.app/'data'):
            with self.assertRaises(OSError) as result:paths.prepare_environment()
        self.assertEqual(result.exception.args[0].error_id,'E_PORTABLE_PATH')

    def test_legacy_discovery_preserves_priority_without_copying(self):
        for name in paths.LEGACY_DIRECTORIES:(self.local/name).mkdir(parents=True)
        self.assertEqual([p.name for p in paths.legacy_roots()],list(paths.LEGACY_DIRECTORIES))
        self.assertFalse(paths.data_root().exists())

    def test_model_runtime_and_cache_consumers_use_portable_layout(self):
        from screento3d_app.optional_models import model_root,PACKS
        from screento3d_app.download_cache import cache_root as downloads
        from screento3d_app.resources import cache_root as engines
        root=paths.prepare_environment()
        self.assertEqual(model_root('vda-small'),root/'models/vda-small'/PACKS['vda-small'].sha[:16])
        self.assertEqual(model_root('trt-core'),root/'runtimes/trt-core'/PACKS['trt-core'].sha[:16])
        self.assertEqual(downloads(),root/'cache/downloads');self.assertEqual(engines(),root/'cache/engines')

    def test_paths_do_not_follow_current_working_directory(self):
        old=Path.cwd();other=self.base/'other';other.mkdir()
        try:
            os.chdir(other);self.assertEqual(paths.data_root(),self.app/'data')
        finally:os.chdir(old)


if __name__=='__main__':unittest.main()
