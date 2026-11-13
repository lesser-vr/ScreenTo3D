import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from screento3d_app.user_data import data_root,migrate_legacy_data


class UserDataTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.base=Path(folder.name);self.old=self.base/'DepthSBS';self.new=self.base/'ScreenTo3D'
        self.enterContext(patch.dict(os.environ,{'LOCALAPPDATA':str(self.base)}))

    def put(self,path,data=b'owned fixture'):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)

    def test_path_discovery_has_no_migration_side_effect(self):
        self.put(self.old/'models/model.plan')
        self.assertEqual(data_root(),self.new)
        self.assertTrue((self.old/'models/model.plan').exists());self.assertFalse(self.new.exists())

    def test_new_install_does_not_create_legacy_data(self):
        self.assertEqual(migrate_legacy_data(),self.new)
        self.assertFalse(self.old.exists())

    def test_whole_root_move_preserves_all_payloads_and_is_repeatable(self):
        names=('models/a/model.plan','downloads/archive.zip','downloads/archive.zip.part','engines/small.plan','logs/old.log')
        for i,name in enumerate(names):self.put(self.old/name,bytes([i])*64)
        original={name:hashlib.sha256((self.old/name).read_bytes()).hexdigest() for name in names}
        self.assertEqual(migrate_legacy_data(),self.new);self.assertFalse(self.old.exists())
        self.assertEqual(migrate_legacy_data(),self.new)
        for name,sha in original.items():self.assertEqual(hashlib.sha256((self.new/name).read_bytes()).hexdigest(),sha)

    def test_interim_root_moves_into_correct_name_without_rebuilding(self):
        interim=self.base/'StereoTo3D';self.put(interim/'models/vda.plan',b'compiled engine')
        migrate_legacy_data();migrate_legacy_data()
        self.assertFalse(interim.exists());self.assertFalse(self.old.exists())
        self.assertEqual((self.new/'models/vda.plan').read_bytes(),b'compiled engine')

    def test_three_roots_merge_in_priority_order_preserving_conflicts(self):
        interim=self.base/'StereoTo3D'
        self.put(self.new/'models/current.plan',b'current')
        self.put(interim/'models/current.plan',b'interim current')
        self.put(interim/'models/shared.plan',b'interim')
        self.put(self.old/'models/shared.plan',b'original')
        self.put(self.old/'models/other.plan',b'other')
        migrate_legacy_data();migrate_legacy_data()
        self.assertEqual((self.new/'models/current.plan').read_bytes(),b'current')
        self.assertEqual((self.new/'models/shared.plan').read_bytes(),b'interim')
        self.assertEqual((self.new/'models/other.plan').read_bytes(),b'other')
        self.assertEqual((interim/'models/current.plan').read_bytes(),b'interim current')
        self.assertEqual((self.old/'models/shared.plan').read_bytes(),b'original')

    def test_interim_launcher_log_is_preserved_until_a_later_current_launch(self):
        interim=self.base/'StereoTo3D';log=interim/'logs/launch.log'
        self.put(log,b'active launcher');self.put(interim/'models/engine.plan')
        with patch.dict(os.environ,{'SCREENTO3D_LAUNCH_LOG':str(log)}):migrate_legacy_data()
        self.assertEqual(log.read_bytes(),b'active launcher')
        self.assertTrue((self.new/'models/engine.plan').exists())
        with patch.dict(os.environ,{'SCREENTO3D_LAUNCH_LOG':''}):migrate_legacy_data()
        self.assertFalse(interim.exists());self.assertEqual((self.new/'logs/launch.log').read_bytes(),b'active launcher')

    def test_launcher_created_logs_do_not_prevent_model_adoption(self):
        self.put(self.new/'logs/launch.log',b'current')
        self.put(self.old/'logs/launch.log',b'historical')
        self.put(self.old/'models/vda/receipt',b'protected receipt')
        migrate_legacy_data()
        self.assertEqual((self.new/'models/vda/receipt').read_bytes(),b'protected receipt')
        self.assertEqual((self.new/'logs/launch.log').read_bytes(),b'current')
        self.assertEqual((self.old/'logs/launch.log').read_bytes(),b'historical')

    def test_merge_never_overwrites_a_new_cache_or_drops_old_conflicts(self):
        self.put(self.new/'models/base/a.plan',b'new')
        self.put(self.old/'models/base/a.plan',b'old')
        self.put(self.old/'models/vda/b.plan',b'other model')
        migrate_legacy_data();migrate_legacy_data()
        self.assertEqual((self.new/'models/base/a.plan').read_bytes(),b'new')
        self.assertEqual((self.old/'models/base/a.plan').read_bytes(),b'old')
        self.assertEqual((self.new/'models/vda/b.plan').read_bytes(),b'other model')

    def test_permission_failure_preserves_files_and_has_localized_error_id(self):
        self.put(self.old/'models/owned.plan')
        with patch.object(Path,'rename',side_effect=PermissionError('private path')):
            with self.assertRaises(OSError) as result:migrate_legacy_data()
        self.assertEqual(result.exception.args[0].error_id,'E_DATA_MIGRATION')
        self.assertNotIn('private path',str(result.exception))
        self.assertTrue((self.old/'models/owned.plan').exists());self.assertFalse(self.new.exists())

    def test_linked_merge_entries_are_not_followed(self):
        self.put(self.old/'linked/payload');self.new.mkdir()
        with patch.object(Path,'is_symlink',lambda path:path.name=='linked'):
            with self.assertRaises(OSError):migrate_legacy_data()
        self.assertTrue((self.old/'linked/payload').exists());self.assertFalse((self.new/'linked').exists())

    def test_all_cache_consumers_share_the_new_namespace(self):
        from screento3d_app.optional_models import model_root,PACKS
        from screento3d_app.download_cache import cache_root as downloads
        from screento3d_app.resources import cache_root as engines
        self.assertEqual(model_root('vda-small'),self.new/'models/vda-small'/PACKS['vda-small'].sha[:16])
        self.assertEqual(downloads(),self.new/'downloads');self.assertEqual(engines(),self.new/'engines')

    def test_store_overlay_never_imports_the_backing_namespace(self):
        self.put(self.old/'models/production.plan');self.new.mkdir()
        resolve=Path.resolve
        def redirected(path,*args,**kwargs):
            if path==self.old:return self.base/'production/DepthSBS'
            if path==self.new:return self.base/'store-private/ScreenTo3D'
            return resolve(path,*args,**kwargs)
        with patch.object(Path,'resolve',redirected),patch.object(Path,'rename') as rename:
            self.assertEqual(migrate_legacy_data(),self.new);rename.assert_not_called()
        self.assertTrue((self.old/'models/production.plan').exists())

    @unittest.skipUnless(os.name=='nt','Windows DPAPI receipt relocation')
    def test_migrated_vda_receipt_remains_gpu_bound_and_usable(self):
        from screento3d_app import engine_cache as cache
        from screento3d_app.optional_models import PACKS,available,installed_path
        device={'uuid':'owned-device','tensorrt':cache.TRT_VERSION};pack=PACKS['vda-small']
        relative=Path('models/vda-small')/pack.sha[:16]/cache.device_key(device)
        folder=self.old/relative
        profiles={}
        for width in (896,924):
            name=f'518x{width}-fp16';profiles[name]={'owned':width}
            for stage in ('warmup','cached'):self.put(folder/name/(stage+'.plan'))
        self.put(folder/'.verified',pack.sha.encode())
        cache.save_record(folder/'build.receipt',dict(source=pack.sha,device=device,profiles=profiles))
        before=(folder/'build.receipt').read_bytes();migrate_legacy_data()
        with patch.object(cache,'device_identity',return_value=device):
            target=installed_path('vda-small');self.assertEqual(target,self.new/relative)
            self.assertEqual((target/'build.receipt').read_bytes(),before)
            self.assertTrue(available('vda-small',target))
            self.assertEqual(cache.local_record(target/'518x896-fp16','vda-small'),{'owned':896})


if __name__=='__main__':unittest.main()
