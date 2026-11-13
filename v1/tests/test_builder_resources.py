import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from zipfile import ZipFile

from screento3d_app import builder_resources as resources,optional_models as models


class BuilderResourcesTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.core=self.root/'runtime';self.core.mkdir()
        (self.core/'builder-layout.json').write_text(json.dumps(resources.LAYOUT))
        self.key='trt-sm120';self.archive=self.root/'resource.zip';self.target=self.root/'cache/revision'
        contents={'nvinfer_builder_resource_sm120_11.dll':b'owned-fixture','TENSORRT-LICENSE.txt':b'fixture-license'}
        self.files={name:dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest()) for name,data in contents.items()}
        with ZipFile(self.archive,'w') as zip:
            for name,data in contents.items():zip.writestr(name,data)
        size=self.archive.stat().st_size;sha=hashlib.sha256(self.archive.read_bytes()).hexdigest()
        spec=dict(filename=self.archive.name,size=size,sha=sha,files=self.files)
        self.enterContext(patch.dict(resources.PACKS,{self.key:spec}))
        self.enterContext(patch.dict(models.PACKS,{self.key:models.Pack('Fixture',self.archive.name,size,sha,'')}))
        self.enterContext(patch.dict(resources.CATALOG,common={}))
        self.enterContext(patch.object(models,'installed_path',side_effect=lambda key:self.target if key==self.key else self.root/'absent'))
        self.enterContext(patch.object(models,'source_for',return_value=self.archive))
        self.enterContext(patch.object(resources,'required_key',return_value=self.key))

    def test_installs_and_verifies_the_selected_pack_without_building_a_model(self):
        with patch.object(models,'optimize',side_effect=AssertionError('Resource DLLs are not model graphs')):
            self.assertEqual(resources.prepare(self.core),[self.target])
            self.assertTrue((self.target/'.verified').is_file())
            self.assertEqual(resources.prepare(self.core),[self.target])
        self.assertTrue(resources.ready(self.key))

    def test_modified_cached_dll_is_rejected_before_search_path_activation(self):
        resources.prepare(self.core)
        (self.target/'nvinfer_builder_resource_sm120_11.dll').write_bytes(b'tampered-data')
        with self.assertRaisesRegex(ValueError,'verification'):resources.prepare(self.core)

    def test_invalid_layout_is_not_trusted(self):
        (self.core/'builder-layout.json').write_text(json.dumps(dict(resources.LAYOUT,extra_path='other.dll')))
        with self.assertRaisesRegex(ValueError,'layout'):resources.prepare(self.core)
        self.assertFalse(self.target.exists())

    def test_remote_download_requires_explicit_install_action(self):
        with patch.object(models,'source_for',return_value='https://example.invalid/resource.zip'):
            self.assertFalse(resources.ready(self.key))
            with self.assertRaisesRegex(ValueError,'Install the GPU runtime'):resources.prepare(self.core)
        self.assertFalse(self.target.exists())

    def test_corrupt_archive_cannot_publish(self):
        data=self.archive.read_bytes();self.archive.write_bytes(data[:-1]+bytes([data[-1]^1]))
        self.assertFalse(resources.ready(self.key))
        with self.assertRaisesRegex(ValueError,'verification'):resources.prepare(self.core)
        self.assertFalse(self.target.exists())

class BuilderMappingTests(unittest.TestCase):
    def test_local_resource_sidecar_precedes_a_configured_remote_origin(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'app';root.mkdir()
            (root/'model-origin.txt').write_text('https://example.invalid/packs')
            local=root.parent/'runtime-packs'/models.PACKS['trt-sm120'].filename
            local.parent.mkdir();local.write_bytes(b'owned-inventory-fixture')
            with patch.object(models,'ROOT',root):
                self.assertEqual(models.source_for('trt-sm120'),local)
                self.assertTrue(models.source_for('da2-base').startswith('https://example.invalid/'))

    def test_known_architectures_and_unknown_gpu_compatibility_pack(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            self.assertEqual(resources.required_key(root,dict(compute_capability=[12,0])), '')
            (root/'builder-layout.json').write_text(json.dumps(resources.LAYOUT))
            for cc,key in (([12,0],'trt-sm120'),([8,9],'trt-sm89'),([12,1],'trt-all')):
                self.assertEqual(resources.required_key(root,dict(compute_capability=cc)),key)

    def test_dll_directory_handles_close_when_later_registration_fails(self):
        from screento3d_app.resources import prepare_dll_search_path
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);extra=root/'gpu';extra.mkdir();first=Mock()
            with patch.object(resources,'prepare',return_value=[extra]),patch('screento3d_app.resources.os.add_dll_directory',side_effect=[first,OSError('fixture')],create=True),patch.dict('os.environ'):
                import os
                original=os.environ.get('PATH','')
                with self.assertRaises(OSError):prepare_dll_search_path(root)
                self.assertEqual(os.environ.get('PATH',''),original)
            first.close.assert_called_once()


if __name__=='__main__':unittest.main()
