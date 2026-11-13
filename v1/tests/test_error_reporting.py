import contextlib
import io
import json
import unittest
from unittest.mock import patch

from screento3d_app.main import build_parser, run_worker
from screento3d_app.messages import ErrorMessage as E,from_payload
from screento3d_app.error_reporting import error_event


class WorkerErrorPrivacyTests(unittest.TestCase):
    def test_typed_errors_keep_id_and_redact_parameters_and_notes_by_default(self):
        error=ValueError(E('E_OUTPUT_FRAME_DELIVERY',v0='C:/private/SECRET',details='SECRET native code'))
        error.add_note('SECRET note')
        event=error_event(error)
        self.assertEqual(event['error_id'],'E_OUTPUT_FRAME_DELIVERY')
        self.assertEqual(from_payload(event['localized']).error_id,'E_OUTPUT_FRAME_DELIVERY')
        self.assertNotIn('SECRET',json.dumps(event))
        detailed=error_event(error,detailed=True)
        self.assertEqual(detailed['error_id'],event['error_id'])
        self.assertIn('SECRET',from_payload(detailed['localized']).details)
        self.assertEqual(detailed['notes'],['SECRET note'])

    def invoke(self, detailed=False, cancellation=False):
        values = ['--mode', 'performance']
        if detailed:
            values.append('--detailed-errors')
        args = build_parser().parse_args(values)
        error = (InterruptedError if cancellation else RuntimeError)(
            'Decode failed: C:/private/secret.mp4 frame-bytes-SECRET')
        error.add_note('cleanup private user/path SECRET')
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch('screento3d_app.pipeline.convert_video', side_effect=error), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = run_worker(args)
        return status, stdout.getvalue(), stderr.getvalue()

    def test_default_error_and_cleanup_do_not_leak_exception_payload(self):
        for cancellation in (False, True):
            with self.subTest(cancellation=cancellation):
                status, output, trace = self.invoke(cancellation=cancellation)
                self.assertEqual(status, 1)
                event = json.loads(output)
                self.assertEqual(event['code'], 'decode')
                self.assertTrue(event['cleanup_failed'])
                self.assertNotIn('SECRET', output + trace)
                self.assertNotIn('private', output + trace)
                self.assertEqual(trace, '')

    def test_detailed_errors_require_explicit_selection(self):
        status, output, trace = self.invoke(detailed=True)
        self.assertEqual(status, 1)
        self.assertIn('SECRET', output)
        self.assertIn('Traceback', trace)
        self.assertFalse(build_parser().parse_args([]).detailed_errors)
