"""Diagnostic adapter keeps artifact integrity and restores product bindings."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import base_trt_fp16_trial as trial
from screento3d_app import da2_base as base, da2_base_device as device


class TrialTrustTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name).resolve(strict=True)
        self.root = self.path / 'checkout'
        self.trusted_directory = self.root / 'out/da2-base-local'
        self.trusted_directory.mkdir(parents=True)
        self.payload = b'local fixture, never deserialized'
        (self.path / 'mixed.plan').write_bytes(self.payload)
        for name, value in (('ROOT', self.root), ('ARTIFACTS', self.path), ('PINS', {'mixed': (
                hashlib.sha256(self.payload).hexdigest(), len(self.payload))})):
            patcher = patch.object(trial, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_scoped_install_restores_after_error(self):
        original = base.checked_plan, base.profiles, base.PROFILES, device.Da2BaseDeviceEngine
        with self.assertRaisesRegex(RuntimeError, 'intentional'):
            with trial.installed('mixed'):
                self.assertEqual(base.checked_plan(self.path, (518, 924)), self.payload)
                with self.assertRaises(ValueError):
                    base.checked_plan(self.path, (518, 896))
                with self.assertRaises(ValueError):
                    base.profiles(self.path)
                self.assertEqual(base.profiles(self.trusted_directory), {(518, 924): self.path})
                raise RuntimeError('intentional')
        self.assertEqual(original, (base.checked_plan, base.profiles, base.PROFILES, device.Da2BaseDeviceEngine))

    def test_integrity_rechecked_before_load(self):
        with trial.installed('mixed'):
            (self.path / 'mixed.plan').write_bytes(b'x' * len(self.payload))
            with self.assertRaisesRegex(ValueError, 'changed'):
                base.checked_plan(self.path, (518, 924))
        with self.assertRaisesRegex(ValueError, 'integrity'):
            trial.manifest('mixed')

    def test_explicit_fp32_control_restores_current_default(self):
        original = base.checked_plan, base.profiles, base.PROFILES, device.Da2BaseDeviceEngine
        precision = base.PRECISION
        with trial.installed('fp32') as info:
            self.assertEqual(info['runtime'], 'tensorrt-fp32')
            self.assertEqual(base.PRECISION, 'fp32')
            self.assertEqual(base.PROFILES, trial.FP32_PROFILES)
        self.assertEqual(original, (base.checked_plan, base.profiles, base.PROFILES, device.Da2BaseDeviceEngine))
        self.assertEqual(base.PRECISION, precision)


if __name__ == '__main__':
    unittest.main()
