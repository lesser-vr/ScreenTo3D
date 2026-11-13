import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from screento3d_app import user_data as paths,portable_import as imports


class PortableImportTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.base=Path(folder.name);self.app=self.base/'app';self.app.mkdir();self.old=self.base/'previous';self.old.mkdir()
        self.enterContext(patch.object(paths,'APP_ROOT',self.app))

    def put(self,relative,data=b'owned data'):
        path=self.old/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);return path

    def test_copy_routes_runtimes_and_caches_and_preserves_sources(self):
        files={'models/vda-small/revision/engine.plan':b'engine','models/trt-core/revision/core.dll':b'runtime',
               'downloads/original.zip':b'archive','engines/small.plan':b'small'}
        for name,data in files.items():self.put(name,data)
        self.put('logs/private.log',b'not imported')
        result=imports.import_files(imports.inventory([self.old]))
        self.assertEqual(result['files'],4);self.assertEqual(result['preserved'],4);root=paths.data_root()
        self.assertEqual((root/'runtimes/trt-core/revision/core.dll').read_bytes(),b'runtime')
        self.assertEqual((root/'cache/downloads/original.zip').read_bytes(),b'archive')
        self.assertEqual((root/'cache/engines/small.plan').read_bytes(),b'small')
        self.assertFalse((root/'logs/private.log').exists())
        for name,data in files.items():self.assertEqual((self.old/name).read_bytes(),data)

    def test_conflicting_current_file_wins_and_original_is_not_removed(self):
        source=self.put('models/unknown/plan',b'old');target=paths.data_root()/'models/unknown/plan'
        target.parent.mkdir(parents=True);target.write_bytes(b'current')
        report=imports.import_files(imports.inventory([self.old]),cleanup=True)
        self.assertEqual(report['conflicts'],1);self.assertEqual(source.read_bytes(),b'old')
        self.assertEqual(target.read_bytes(),b'current')

    def test_cleanup_is_opt_in_and_never_removes_other_files(self):
        source=self.put('engines/small.plan');other=self.put('user-notes.txt',b'preserve')
        items=imports.inventory([self.old]);imports.import_files(items)
        self.assertTrue(source.exists())
        report=imports.import_files(items,cleanup=True)
        self.assertEqual(report['removed'],1);self.assertFalse(source.exists())
        self.assertEqual(other.read_bytes(),b'preserve');self.assertTrue(self.old.exists())

    def test_insufficient_space_stops_before_copy(self):
        source=self.put('engines/plan');items=imports.inventory([self.old])
        with patch.object(imports.shutil,'disk_usage',return_value=SimpleNamespace(free=0)):
            with self.assertRaises(OSError) as result:imports.import_files(items)
        self.assertEqual(result.exception.args[0].error_id,'E_DATA_IMPORT_SPACE');self.assertTrue(source.exists())
        self.assertFalse((paths.data_root()/'cache/engines/plan').exists())

    def test_cancel_cleans_partial_stage_and_retains_original(self):
        source=self.put('engines/plan',b'x'*(2*1024**2));items=imports.inventory([self.old]);stop=[False]
        def progress(done,total):stop[0]=True
        with self.assertRaises(InterruptedError):imports.import_files(items,progress,lambda:stop[0],cleanup=True)
        self.assertTrue(source.exists());self.assertFalse((paths.data_root()/'cache/engines/plan').exists())
        self.assertFalse(list(paths.data_root().rglob('.import-*')))

    def test_changed_source_rejected_and_not_deleted(self):
        source=self.put('engines/plan');items=imports.inventory([self.old]);source.write_bytes(b'changed source')
        with self.assertRaises(OSError) as result:imports.import_files(items,cleanup=True)
        self.assertEqual(result.exception.args[0].error_id,'E_DATA_IMPORT_CHANGED');self.assertTrue(source.exists())

    def test_verification_failure_preserves_all_sources_including_earlier_files(self):
        a=self.put('engines/a.plan');b=self.put('engines/b.plan');items=sorted(imports.inventory([self.old]),key=lambda item:str(item['relative']))
        original=imports._hash;count=[0]
        def digest(path,cancelled):
            value=original(path,cancelled)
            if path.name.startswith('.import-'):
                count[0]+=1
                if count[0]==2:return 'invalid digest'
            return value
        with patch.object(imports,'_hash',digest),self.assertRaises(OSError) as result:imports.import_files(items,cleanup=True)
        self.assertEqual(result.exception.args[0].error_id,'E_DATA_IMPORT_VERIFY')
        self.assertTrue(a.exists() and b.exists());self.assertFalse(list(paths.data_root().rglob('.import-*')))

    def test_cleanup_retains_a_source_changed_after_copy(self):
        source=self.put('engines/plan');items=imports.inventory([self.old]);original=imports._hash
        def digest(path,cancelled):
            value=original(path,cancelled)
            if path==paths.data_root()/'cache/engines/plan':source.write_bytes(b'new source')
            return value
        with patch.object(imports,'_hash',digest):report=imports.import_files(items,cleanup=True)
        self.assertEqual(report['preserved'],1);self.assertEqual(source.read_bytes(),b'new source')

    def test_nested_links_are_rejected_before_copy(self):
        self.put('models/linked/plan')
        with patch.object(Path,'is_symlink',lambda path:path.name=='linked'):
            with self.assertRaises(OSError):imports.inventory([self.old])
        self.assertFalse(paths.data_root().exists())

    def test_source_destination_overlap_rejected(self):
        with self.assertRaises(OSError):imports.inventory([self.app])

    def test_multiple_legacy_sources_keep_the_first_revision(self):
        self.put('engines/plan',b'preferred');older=self.base/'older';(older/'engines').mkdir(parents=True);(older/'engines/plan').write_bytes(b'older')
        report=imports.import_files(imports.inventory([self.old,older]))
        self.assertEqual(report['files'],1);self.assertEqual((paths.data_root()/'cache/engines/plan').read_bytes(),b'preferred')


if __name__=='__main__':unittest.main()
