import unittest
from unittest.mock import Mock

from live_benchmark_source import SourceProcess


class SourceProtocolTests(unittest.TestCase):
    def make_source(self):
        source = object.__new__(SourceProcess)
        source.process = Mock()
        source.connection = Mock()
        source.timeout = 0.1
        source.closed = False
        return source

    def test_timeout_is_visible(self):
        source = self.make_source()
        source.connection.poll.return_value = False
        with self.assertRaises(TimeoutError):
            source._receive()
        source.connection.recv.assert_not_called()

    def test_eof_is_visible(self):
        source = self.make_source()
        source.connection.recv.side_effect = EOFError
        with self.assertRaisesRegex(RuntimeError, "exited"):
            source._receive()

    def test_dead_child_not_sent_commands(self):
        source = self.make_source()
        source.process.is_alive.return_value = False
        with self.assertRaises(RuntimeError):
            source.refresh()
        source.connection.send.assert_not_called()

    def test_invalid_resize_not_sent(self):
        source = self.make_source()
        for shape in ((0, 10), (-1, 10), (True, 10), (2.5, 10)):
            with self.assertRaises(ValueError):
                source.resize(*shape)
        source.connection.send.assert_not_called()

    def test_failed_stop_terminates_only_owned_child(self):
        source = self.make_source()
        source.connection.poll.return_value = False
        source.process.is_alive.side_effect = [True, True, True, False, False]
        source.close()
        source.process.terminate.assert_called_once()
        source.connection.close.assert_called_once()
        source.close()
        source.process.terminate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
