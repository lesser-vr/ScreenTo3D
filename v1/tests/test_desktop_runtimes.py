import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from io import BytesIO
from zipfile import ZipFile
from depthsbs_app import desktop_runtimes as runtimes,optional_models as models


class DesktopRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.target=self.root/'cache/version';self.key='media-tools'
        self.archive=self.root/'owned.zip';self.contents={'ffmpeg.exe':b'owned media fixture','licenses/LICENSE.txt':b'owned license'}
        with ZipFile(self.archive,'w') as archive:
            for name,data in self.contents.items():archive.writestr(name,data)
        self.pack=dict(filename=self.archive.name,size=self.archive.stat().st_size,sha=hashlib.sha256(self.archive.read_bytes()).hexdigest(),
            files={name:dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest()) for name,data in self.contents.items()})
        self.enterContext(patch.dict(runtimes.PACKS,{self.key:self.pack}))
        self.enterContext(patch.dict(models.PACKS,{self.key:models.Pack('Owned fixture',self.pack['filename'],self.pack['size'],self.pack['sha'],'')}))
        self.enterContext(patch.object(models,'installed_path',return_value=self.target))
        self.marker=self.root/'app/ffmpeg';self.marker.mkdir(parents=True)
        (self.marker/'component-layout.json').write_text(json.dumps(dict(schema=1,component=self.key)))

    def install(self,cancel=lambda:False,source=None):
        with patch.object(models,'optimize',side_effect=AssertionError('Components must not optimize models')):
            return models.install(self.key,source or self.archive,self.target,lambda *_:None,cancel)

    def test_only_verified_complete_payload_can_be_loaded_from_marker_or_cache(self):
        with self.assertRaisesRegex(ValueError,'media tools'):runtimes.resolve(self.marker,self.key)
        self.install();self.assertEqual(runtimes.resolve(self.marker,self.key),self.target)
        self.assertEqual(runtimes.resolve(self.target,self.key),self.target)
        (self.target/'ffmpeg.exe').write_bytes(b'tampered media data')
        with self.assertRaisesRegex(ValueError,'verification'):runtimes.resolve(self.target,self.key)

    def test_cancelled_or_corrupt_download_never_publishes_and_retry_works(self):
        with self.assertRaises(InterruptedError):self.install(lambda:True)
        self.assertFalse(self.target.exists())
        bad=self.root/'bad.zip';bad.write_bytes(b'bad')
        with self.assertRaises(ValueError):self.install(source=bad)
        self.assertFalse(self.target.exists());self.install();self.assertTrue(models.available(self.key,self.target))
        self.assertFalse(list(self.target.parent.glob('.install-*')))

    def test_https_download_uses_pinned_archive_and_rejects_redirect_downgrade(self):
        response=BytesIO(self.archive.read_bytes());response.geturl=lambda:'https://download.example/component.zip'
        with patch.object(models,'urlopen',return_value=response):self.install(source='https://download.example/component.zip')
        self.assertTrue(models.available(self.key,self.target))
        other=self.root/'other';response=BytesIO(self.archive.read_bytes());response.geturl=lambda:'http://download.example/component.zip'
        with patch.object(models,'urlopen',return_value=response),self.assertRaisesRegex(ValueError,'secure connection'):
            models.install(self.key,'https://download.example/component.zip',other,lambda *_:None,lambda:False)
        self.assertFalse(other.exists())

    def test_local_pack_wins_over_origin_and_catalog_controls_extracted_inventory(self):
        root=self.root/'portable';root.mkdir();(root/'model-origin.txt').write_text('https://example.invalid/downloads')
        packs=root.parent/'runtime-packs';packs.mkdir();(packs/self.pack['filename']).write_bytes(b'owned locator fixture')
        with patch.object(models,'ROOT',root):self.assertEqual(models.source_for(self.key),packs/self.pack['filename'])
        self.install();(self.target/'unexpected.dll').write_bytes(b'untrusted')
        with self.assertRaisesRegex(ValueError,'verification'):runtimes.resolve(self.target,self.key)

    def test_legacy_bundled_directories_remain_explicit_and_marker_is_exact(self):
        plain=self.root/'bundled';plain.mkdir();self.assertEqual(runtimes.resolve(plain,self.key),plain)
        (self.marker/'component-layout.json').write_text(json.dumps(dict(schema=1,component='other')))
        with self.assertRaises(ValueError):runtimes.resolve(self.marker,self.key)


if __name__=='__main__':unittest.main()
