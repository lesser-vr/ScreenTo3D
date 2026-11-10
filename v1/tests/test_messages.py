import importlib.util
import json
import pickle
import gc
import weakref
from pathlib import Path
import subprocess
import sys
import unittest

from depthsbs_app.messages import Message as M, decode_message, encode_message, from_payload, joined, payload


class MessageTests(unittest.TestCase):
    def test_nested_messages_and_exception_keep_template_across_worker_boundary(self):
        value=M('Failure: {detail}',detail=ValueError(M('Item {number}',number=7)))
        restored=decode_message(encode_message(value))
        self.assertEqual(str(restored),'Failure: Item 7')
        self.assertEqual(restored.source,'Failure: {detail}')
        self.assertEqual(restored.values['detail'].source,'Item {number}')

    def test_join_keeps_arguments_and_opaque_diagnostics(self):
        value=joined('\n',('raw <source title>',M('Stage {number}',number=3)))
        restored=from_payload(json.loads(json.dumps(payload(value))))
        self.assertEqual(str(restored),'raw <source title>\nStage 3')
        self.assertEqual(restored.parts[2].values,dict(number=3))

    def test_transport_is_bounded_and_valid_utf8(self):
        for value in ('한글'*1000,M('Error: {detail}',detail='한글'*1000)):
            wire=encode_message(value,limit=80)
            self.assertLessEqual(len(wire),80)
            wire.decode('utf-8',errors='strict')
            self.assertFalse(wire.startswith(b'ScreenTo3D-message-v1:'))
        self.assertEqual(decode_message(b'opaque error code 5'),'opaque error code 5')

    def test_process_snapshot_handles_literal_braces_in_values(self):
        value='Prefix · '+M('Window {title}',title='Game {opaque}')
        restored=pickle.loads(pickle.dumps(value))
        self.assertEqual(str(restored),'Prefix · Window Game {opaque}')
        self.assertEqual(restored.parts[1].values,dict(title='Game {opaque}'))

    def test_stored_message_does_not_retain_exception_resources(self):
        class Owner:pass
        def failed_operation():
            owner=Owner();reference=weakref.ref(owner)
            try:raise RuntimeError('opaque failure')
            except RuntimeError as error:message=M('Failure: {error}',error=error)
            return message,reference
        message,reference=failed_operation();gc.collect()
        self.assertEqual(str(message),'Failure: opaque failure')
        self.assertIsNone(reference())

    def test_malformed_payload_remains_opaque(self):
        for value in ('ScreenTo3D-message-v1:{', 'ScreenTo3D-message-v1:{"parts":17}'):
            self.assertEqual(decode_message(value),value)
        with self.assertRaises(ValueError):from_payload(dict(source='{a}',values={'a-b':1}))
        for source in ('{a:1000000000}','{a.__class__}','{a:{b}}'):
            with self.assertRaises(ValueError):from_payload(dict(source=source,values={'a':'value'}))

    def test_worker_messages_do_not_import_qt(self):
        command='import sys; from depthsbs_app.messages import Message; assert not any(n.startswith("PySide6") for n in sys.modules)'
        subprocess.run([sys.executable,'-c',command],check=True)

    def test_catalog_covers_english_sources_and_preserves_placeholders(self):
        root=Path(__file__).resolve().parents[2]
        spec=importlib.util.spec_from_file_location('translation_build',root/'scripts/build-translations.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.assertGreater(module.validate(root/'v1/depthsbs_app/translations/screento3d_ko.ts'),300)
