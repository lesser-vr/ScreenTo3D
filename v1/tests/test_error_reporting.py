import contextlib
import io
import json
import unittest
from unittest.mock import patch

from depthsbs_app.main import build_parser, run_worker


class WorkerErrorPrivacyTests(unittest.TestCase):
    def invoke(self, detailed=False, cancellation=False):
        args = build_parser().parse_args(['--detailed-errors'] if detailed else [])
        error = (InterruptedError if cancellation else RuntimeError)(
            'Decode failed: C:/private/secret.mp4 frame-bytes-SECRET')
        error.add_note('cleanup private user/path SECRET')
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch('depthsbs_app.pipeline.convert_video', side_effect=error), \
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
