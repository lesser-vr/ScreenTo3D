import unittest
from pathlib import Path
from unittest.mock import patch
from depthsbs_app import da2_base


class ProfileTests(unittest.TestCase):
    def test_resolution_mapping_and_fail_closed_selection(self):
        installed = {(518,896): Path('original'), (518,924): Path('wide')}
        with patch.object(da2_base, 'profiles', return_value=installed), patch.object(Path, 'is_file', return_value=True), patch.object(da2_base, 'Da2BaseEngine') as engine:
            backend = da2_base.binding(Path('root'), Path('runtime'))
            with self.assertRaises(ValueError): backend.engine_factory(None)
            for w,h in ((1280,720),(1920,1080),(3840,2160)):
                backend.input_validator(dict(width=w,height=h))
                backend.engine_factory(None)
                self.assertEqual(engine.call_args.args[-1], (518,924))
            backend.input_validator(dict(width=1056,height=608))
            backend.engine_factory(None)
            self.assertEqual(engine.call_args.args[-1], (518,896))
            with self.assertRaises(ValueError): backend.input_validator(dict(width=608,height=1056))
            with self.assertRaises(ValueError): backend.engine_factory(None)

    def test_corrupt_same_size_plan_rejected(self):
        with patch.object(Path,'resolve',lambda self,strict=True:self), patch.object(Path,'stat') as stat, patch.object(Path,'read_bytes',return_value=b'bad'):
            stat.return_value.st_size = da2_base.PLAN_BYTES
            with self.assertRaisesRegex(ValueError,'checksum'):
                da2_base.checked_plan(Path('artifact'))
