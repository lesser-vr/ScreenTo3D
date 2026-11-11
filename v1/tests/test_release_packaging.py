import importlib.util,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('desktop_release_package',ROOT/'scripts/package-desktop-release.py')
packager=importlib.util.module_from_spec(spec);spec.loader.exec_module(packager)


class ReleasePackagingTests(unittest.TestCase):
    def run_package(self,maximum=None):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        folder=Path(temp.name);app=folder/'ScreenTo3D-1.0.0';app.mkdir()
        (app/'build-manifest.json').write_text(json.dumps(dict(product_version='1.0.0',source_commit='owned-fixture')))
        for index in range(4):(app/f'owned-{index}.bin').write_bytes(bytes(range(256)))
        output=folder/'assets'
        with patch.object(packager,'MAX_ASSET',maximum or packager.MAX_ASSET):packager.package(app,output,None)
        manifest=json.loads((output/'release-manifest.json').read_text())
        seen=set()
        for asset in manifest['assets']:
            archive=output/asset['name']
            self.assertEqual(packager.digest(archive),asset['sha256'])
            with ZipFile(archive) as zip:
                for entry in zip.infolist():
                    self.assertNotIn(entry.filename,seen);seen.add(entry.filename)
                    self.assertEqual(zip.read(entry), (folder/entry.filename).read_bytes())
        self.assertEqual(len(seen),5)
        return manifest

    def test_one_archive_has_plain_filename_and_matching_manifest(self):
        manifest=self.run_package()
        self.assertEqual([a['name'] for a in manifest['assets']],['ScreenTo3D-1.0.0-windows-x64.zip'])

    def test_multiple_archives_keep_numbered_names_and_disjoint_contents(self):
        manifest=self.run_package(32*1024**2+384)
        self.assertGreater(len(manifest['assets']),1)
        for index,asset in enumerate(manifest['assets'],1):
            self.assertEqual(asset['name'],f'ScreenTo3D-1.0.0-windows-x64-part{index:02d}.zip')


if __name__=='__main__':unittest.main()
