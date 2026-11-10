import importlib.util
import json
import pickle
import gc
import weakref
from pathlib import Path
import subprocess
import sys
import unittest
import tempfile
from unittest.mock import patch

from depthsbs_app.messages import Message as M, ErrorMessage as E, as_error, decode_message, encode_message, from_payload, joined, payload


class MessageTests(unittest.TestCase):
    def test_error_identity_survives_serialization_pickle_and_rewording(self):
        from depthsbs_app.catalogs import ERRORS
        value=E('E_OUTPUT_FRAME_DELIVERY',v0='driver {opaque}',details='native code 5')
        for restored in (decode_message(encode_message(ValueError(value))),pickle.loads(pickle.dumps(value))):
            self.assertEqual(restored.error_id,value.error_id)
            self.assertEqual(restored.values,value.values)
            self.assertEqual(restored.details,'native code 5')
        wire=payload(value)
        self.assertNotIn('source',wire)
        with patch.dict(ERRORS,{'E_OUTPUT_FRAME_DELIVERY':dict(source='New wording: {v0}',public='Output failed.',category='conversion')}):
            restored=from_payload(wire)
            self.assertEqual(restored.error_id,'E_OUTPUT_FRAME_DELIVERY')
            self.assertEqual(str(restored),'New wording: driver {opaque}')

    def test_bounded_error_preserves_id_and_valid_metadata(self):
        value=E('E_OUTPUT_FRAME_DELIVERY',v0='한글'*4000,details='opaque'*4000)
        for limit in (250,500,1000):
            wire=encode_message(value,limit=limit)
            self.assertLessEqual(len(wire),limit)
            restored=decode_message(wire)
            self.assertIsInstance(restored,E)
            self.assertEqual(restored.error_id,value.error_id)
            self.assertIn('Direct GPU frame delivery failed:',str(restored))
        self.assertIn(b'E_OUTPUT_FRAME_DELIVERY',encode_message(value,limit=80))

    def test_unknown_error_id_keeps_diagnostics_and_invalid_payload_stays_opaque(self):
        value=E('E_FUTURE_DRIVER',details='native driver result 17')
        restored=decode_message(encode_message(value))
        self.assertEqual(restored.error_id,'E_FUTURE_DRIVER')
        self.assertEqual(restored.details,'native driver result 17')
        self.assertIn('unknown',str(restored))
        for changes in (dict(error_id='../bad'),dict(details=42),dict(public='yes'),dict(values={'not-valid':1}),dict(values={})):
            wire=payload(E('E_OUTPUT_FRAME_DELIVERY',v0='opaque'));wire.update(changes)
            encoded='ScreenTo3D-message-v1:'+json.dumps(wire)
            self.assertEqual(decode_message(encoded),encoded)

    def test_error_boundary_and_mailbox_keep_id_without_qt_or_exception_owners(self):
        from depthsbs_app.capture_mailbox import Mailbox
        import multiprocessing as mp
        mailbox=Mailbox.create(mp.get_context('spawn'),metadata_only=True)
        mailbox.fail(ValueError(E('E_CAPTURE_SOURCE_CLOSED')))
        self.assertEqual(decode_message(mailbox.error.value).error_id,'E_CAPTURE_SOURCE_CLOSED')
        self.assertEqual(as_error(M('The selected window closed. Select another window.')).error_id,'E_CAPTURE_SOURCE_CLOSED')
        self.assertEqual(as_error('native failure').details,'native failure')

    def test_registry_rejects_escaping_paths_and_duplicate_languages(self):
        from depthsbs_app.catalogs import load_languages,load_errors
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'registry.json'
            def language(catalog):return dict(code='en',name='English',locale='en-US',catalog=catalog)
            for languages in ([language('../escape')],[language(None),language(None)]):
                path.write_text(json.dumps(dict(schema=1,default='en',languages=languages)),encoding='utf-8')
                with self.assertRaises(ValueError):load_languages(path)
            path.write_text(json.dumps(dict(schema=1,errors={'E_TEST':dict(source='Failure {value.__class__}',public='Failure')})),encoding='utf-8')
            with self.assertRaises(ValueError):load_errors(path)

    def test_registered_language_scaffolds_and_generates_native_table(self):
        root=Path(__file__).resolve().parents[2]
        spec=importlib.util.spec_from_file_location('translation_build_extra',root/'scripts/build-translations.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        languages={**module.definitions.LANGUAGES,'de':dict(code='de',name='Deutsch',locale='de-DE',catalog='screento3d_de')}
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'screento3d_de.ts';module.update(path,'de-DE')
            with self.assertRaisesRegex(ValueError,'Unfinished translation'):module.validate(path)
            import xml.etree.ElementTree as ET
            tree=ET.parse(path)
            for context in tree.getroot().findall('context'):
                for message in context.findall('message'):
                    source=message.findtext('source')
                    if context.findtext('name') in ('Errors','PublicErrors'):
                        source=message.findtext('extracomment')
                    translation=message.find('translation');translation.attrib.clear();translation.text=source
            tree.write(path,encoding='utf-8')
            catalog=module.read_catalog(path)
            header=module.native_header(languages,{'de':catalog})
            self.assertIn('L"de", L"de-DE"',header)
            self.assertIn('E_LAUNCH_COMPONENTS',header)
            # Error translation keys are IDs; validate parameters against templates.
            context=next(c for c in tree.getroot().findall('context') if c.findtext('name')=='Errors')
            entry=next(m for m in context.findall('message') if m.findtext('source')=='E_OUTPUT_FRAME_DELIVERY')
            entry.find('translation').text='Invalid missing parameter'
            tree.write(path,encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'placeholders differ'):module.validate(path)

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
        source=Path(__file__).resolve().parents[1]
        command=(f'import sys; sys.path.insert(0,{str(source)!r}); '
                 'from depthsbs_app.messages import ErrorMessage; ErrorMessage("E_UNKNOWN"); '
                 'assert not any(n.startswith("PySide6") for n in sys.modules)')
        subprocess.run([sys.executable,'-I','-S','-c',command],check=True)

    def test_catalog_covers_english_sources_and_preserves_placeholders(self):
        root=Path(__file__).resolve().parents[2]
        spec=importlib.util.spec_from_file_location('translation_build',root/'scripts/build-translations.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.assertGreater(module.validate(root/'v1/depthsbs_app/translations/screento3d_ko.ts'),300)
