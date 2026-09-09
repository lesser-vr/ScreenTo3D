import subprocess
import unittest
from unittest.mock import Mock

from distill_gpu_motion import Encoder


class EncoderCleanupTests(unittest.TestCase):
    def encoder(self):
        encoder = Encoder.__new__(Encoder)
        encoder.process = Mock()
        encoder.process.poll.return_value = None
        encoder.process.wait.return_value = 0
        encoder.log = Mock()
        return encoder

    def test_broken_pipe_still_reaps_owned_process(self):
        encoder = self.encoder()
        encoder.process.stdin.close.side_effect = BrokenPipeError()
        with self.assertRaises(RuntimeError):
            encoder.close()
        encoder.process.terminate.assert_called_once()
        encoder.process.wait.assert_called_once_with(timeout=30)
        encoder.log.close.assert_called_once()

    def test_failure_cleanup_reaps_without_masking_original_pipe_error(self):
        encoder = self.encoder()
        encoder.process.stdin.close.side_effect = BrokenPipeError()
        encoder.close(failed=True)
        encoder.process.wait.assert_called_once()
        encoder.log.close.assert_called_once()

    def test_timeout_kills_and_reaps(self):
        encoder = self.encoder()
        encoder.process.wait.side_effect = [subprocess.TimeoutExpired('owned', 30), 1]
        with self.assertRaises(RuntimeError):
            encoder.close()
        encoder.process.kill.assert_called_once()
        self.assertEqual(encoder.process.wait.call_count, 2)
        encoder.log.close.assert_called_once()
