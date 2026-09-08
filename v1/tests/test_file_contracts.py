import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from depthsbs_app import pipeline


class InputProtectionTests(unittest.TestCase):
    def test_same_input_and_normalized_alias_fail_before_probe(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'input.mp4'
            source.write_bytes(b'original input')
            for output in (source, source.parent / 'unused' / '..' / source.name):
                events = []
                with self.subTest(output=output), patch.object(pipeline, 'probe_video') as probe:
                    with self.assertRaisesRegex(ValueError, 'must differ'):
                        pipeline.convert_video(source, output, 'balanced', events.append)
                    probe.assert_not_called()
                self.assertEqual(source.read_bytes(), b'original input')
                self.assertEqual(events, [])
                self.assertEqual(list(source.parent.iterdir()), [source])

    def test_hardlink_and_cancel_aliases_preserve_input_before_probe(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'input.mp4'
            source.write_bytes(b'original')
            alias = root / 'alias.mp4'
            alias.hardlink_to(source)
            for output, cancel in ((alias, None), (root/'out.mp4', source),
                                   (root/'out.mp4', alias)):
                with self.subTest(output=output, cancel=cancel), patch.object(pipeline, 'probe_video') as probe:
                    with self.assertRaises(ValueError):
                        pipeline.convert_video(source, output, 'balanced', lambda event: None, cancel)
                    probe.assert_not_called()
                self.assertEqual(source.read_bytes(), b'original')
                self.assertEqual(alias.read_bytes(), b'original')
