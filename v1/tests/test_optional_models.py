import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from depthsbs_app import optional_models as models


class OptionalInstallTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.archive = self.root/'pack.zip'
        with ZipFile(self.archive, 'w') as z:
            z.writestr('518x924-fp16/model.plan', b'fixture')
        data = self.archive.read_bytes()
        self.pack = models.Pack('Test', self.archive.name, len(data), hashlib.sha256(data).hexdigest(), '')
        self.enterContext(patch.dict(models.PACKS, {'da2-base': self.pack}))
        self.enterContext(patch.object(models, 'optimize'))
        self.target = self.root/'installed'/'revision'

    def install(self, cancel=lambda: False):
        return models.install('da2-base', self.archive, self.target, lambda *args: None, cancel)

    def test_cancel_then_retry_and_duplicate_publication(self):
        with self.assertRaises(InterruptedError):
            self.install(cancel=lambda: True)
        self.assertEqual(list(self.target.parent.iterdir()), [])
        self.install()
        self.install()
        self.assertEqual((self.target/'518x924-fp16/model.plan').read_bytes(), b'fixture')
        self.assertEqual((self.target/'.verified').read_text(), self.pack.sha)

    def test_corrupt_download_never_publishes(self):
        data = self.archive.read_bytes()
        self.archive.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
        with self.assertRaisesRegex(ValueError, 'verification'):
            self.install()
        self.assertEqual(list(self.target.parent.iterdir()), [])

    def test_interrupted_gpu_build_does_not_publish(self):
        with patch.object(models, 'optimize', side_effect=InterruptedError):
            with self.assertRaises(InterruptedError):
                self.install()
        self.assertEqual(list(self.target.parent.iterdir()), [])

    def test_device_cache_is_separate_and_reusable(self):
        with patch('depthsbs_app.engine_cache.device_identity', return_value={'uuid': 'device-a'}):
            path = models.installed_path('da2-base')
        with patch('depthsbs_app.engine_cache.device_identity', return_value={'uuid': 'device-b'}):
            self.assertNotEqual(models.installed_path('da2-base'), path)
        with patch('depthsbs_app.engine_cache.device_identity', return_value={'uuid': 'device-a'}):
            self.assertEqual(models.installed_path('da2-base'), path)

    def test_public_default_and_distributor_override_keep_the_same_hash_identity(self):
        with patch.object(models,'ROOT',self.root/'app'):
            app=self.root/'app';app.mkdir()
            self.assertEqual(models.source_for('da2-base'),models.MODEL_ORIGIN+'/'+self.pack.filename)
            (app/'model-origin.txt').write_text('https://example.test/fixed-version/\n')
            self.assertEqual(models.source_for('da2-base'),'https://example.test/fixed-version/'+self.pack.filename)
            self.assertEqual(models.model_downloads('https://example.test/fixed-version')['da2-base']['sha256'],self.pack.sha)
            (app/'model-origin.txt').write_text('http://example.test')
            with self.assertRaises(ValueError):models.source_for('da2-base')

    def test_other_existing_directory_is_preserved(self):
        self.target.mkdir(parents=True)
        sentinel = self.target/'user-data'
        sentinel.write_bytes(b'preserve')
        with self.assertRaises(OSError):
            self.install()
        self.assertEqual(sentinel.read_bytes(), b'preserve')

    @unittest.skipUnless(os.name == 'nt', 'Windows user-bound receipt')
    def test_vda_fp32_and_mixed_receipts_are_revision_specific(self):
        from depthsbs_app import engine_cache
        from depthsbs_app.vda_artifacts import artifact_profiles, uses_mixed_fp16
        device = {'uuid': 'gpu-a'}
        with patch.dict(os.environ, LOCALAPPDATA=str(self.root)), patch.object(engine_cache, 'device_identity', return_value=device):
            for source, suffix in ((models.PACKS['vda-small'].sha, 'fp16'), (engine_cache.VDA_FP32_PACK, 'fp32')):
                root = models.model_root('vda-small').parent/source[:16]/engine_cache.device_key(device)
                records = {}
                for width in (896, 924):
                    folder = root/f'518x{width}-{suffix}'
                    folder.mkdir(parents=True)
                    pins = {}
                    for name in ('warmup', 'cached'):
                        data = f'{width} {name} {suffix}'.encode()
                        (folder/f'{name}.plan').write_bytes(data)
                        pins[name] = dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
                    records[folder.name] = dict(input_shape=[1,1,3,518,width], engines=pins)
                receipt = dict(source=source, device=device, profiles=records)
                engine_cache.save_record(root/'build.receipt', receipt)
                self.assertEqual(set(artifact_profiles(root)), {(518,896),(518,924)})
                self.assertEqual(uses_mixed_fp16(root), suffix == 'fp16')
                engine_cache.save_record(root/'build.receipt', dict(receipt, source='wrong revision'))
                with self.assertRaises(ValueError):
                    artifact_profiles(root)

    @unittest.skipUnless(os.name == 'nt', 'Windows user-bound receipt')
    def test_local_plan_rejects_modified_bytes_receipt_and_foreign_device(self):
        from depthsbs_app import engine_cache
        from depthsbs_app.da2_base import checked_plan
        device = {'uuid': 'gpu-a'}
        with patch.dict(os.environ, LOCALAPPDATA=str(self.root)), patch.object(engine_cache, 'device_identity', return_value=device):
            root = models.installed_path('da2-base')
            profile = root/'518x896-fp16'
            profile.mkdir(parents=True)
            plan = profile/'model.plan'
            plan.write_bytes(b'locally tested')
            pin = dict(bytes=plan.stat().st_size, sha256=hashlib.sha256(plan.read_bytes()).hexdigest())
            receipt = root/'build.receipt'
            engine_cache.save_record(receipt, dict(source=self.pack.sha, device=device,
                                     profiles={profile.name: {'engines': {'model': pin}}}))
            self.assertEqual(checked_plan(profile), plan.read_bytes())
            with patch.object(engine_cache, 'device_identity', return_value={'uuid': 'gpu-b'}):
                with self.assertRaises(ValueError):
                    checked_plan(profile)
            plan.write_bytes(b'locally edited')
            with self.assertRaises(ValueError):
                checked_plan(profile)
            receipt.write_bytes(b'edited')
            with self.assertRaises(ValueError):
                checked_plan(profile)
