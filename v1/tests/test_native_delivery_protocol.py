import multiprocessing as mp
import os
import unittest
from unittest.mock import Mock

from depthsbs_app.native_delivery import NativeDelivery
from depthsbs_app.texture_mailbox import (
    TextureMailbox,
    TexturePool,
    TextureFrame,
    OFFERED,
    RETIRED,
)


class NativeProtocolTests(unittest.TestCase):
    def setUp(self):
        self.box = TextureMailbox.create(mp.get_context("spawn"))
        self.pool = TexturePool(1, 1, os.getpid(), 640, 180, 2, -1, (100, 104))
        self.box.offer(self.pool, session=1, owned_pid=os.getpid())
        self.consumer = NativeDelivery.__new__(NativeDelivery)
        self.consumer.dll = Mock()
        self.consumer.dll.native_error.return_value = b""
        self.consumer.dll.native_begin.return_value = 1
        self.consumer.frames = {}
        self.consumer.begin(1)
        self.released = [0, 0]
        self.latest = None

        def release_old():
            if self.latest is not None:
                slot, sequence = self.latest
                self.released[slot] = sequence
                self.latest = None

        def publish(session, generation, slot, sequence):
            release_old()
            self.latest = (slot, sequence)
            return 1

        def releases(output):
            output[:] = self.released
            return 1

        self.consumer.dll.native_publish.side_effect = publish
        self.consumer.dll.native_retire.side_effect = release_old
        self.consumer.dll.native_releases.side_effect = releases

    def consume(self):
        return self.consumer.consume(self.box, os.getpid())

    def test_install_validates_owned_pid_before_native_import(self):
        with self.assertRaises(ValueError):
            self.consumer.consume(self.box, os.getpid() + 1)
        self.consumer.dll.native_install.assert_not_called()

    def test_failed_native_import_is_not_acknowledged(self):
        self.consumer.dll.native_install.return_value = 0
        with self.assertRaises(RuntimeError):
            self.consume()
        self.assertEqual(self.box.state(), OFFERED)
        self.assertIsNone(self.consumer.pool)

    def test_two_pending_slots_and_duplicate_poll(self):
        self.consume()
        first, second = TextureFrame(1, 1, 0, 1, 0, 0), TextureFrame(1, 1, 1, 2, 0, 0)
        self.box.publish(first)
        self.box.publish(second)
        self.assertTrue(self.consume())
        self.assertEqual(self.box.pending(1, 1), (second,))
        self.assertEqual(self.consumer.frames, {1: second})
        self.assertFalse(self.consume())
        self.assertEqual(self.consumer.dll.native_publish.call_count, 2)

    def test_retirement_drops_latest_and_waits_for_release(self):
        self.consume()
        self.box.publish(TextureFrame(1, 1, 0, 1, 0, 0))
        self.consume()
        self.box.retire(1, 1)
        self.consume()
        self.assertEqual(self.box.state(), RETIRED)
        self.assertIsNone(self.consumer.pool)
        self.assertFalse(self.consumer.has_frame)
        self.consumer.dll.native_drop_pool.assert_called_once()

    def test_consumer_failure_is_visible_without_advancing_metadata(self):
        self.consumer.dll.native_error.return_value = b"GPU copy failed"
        with self.assertRaisesRegex(RuntimeError, "GPU copy failed"):
            self.consume()
        self.assertEqual(self.box.state(), OFFERED)

    def test_retirement_waits_for_matching_final_lease_ack(self):
        self.consume()
        frame = TextureFrame(1, 1, 0, 7, 0, 0)
        self.box.publish(frame)
        self.consume()
        # Metadata retirement is not GPU completion. Hold the final lease.
        self.consumer.dll.native_retire.side_effect = lambda: None
        self.box.retire(1, 1)
        self.consume()
        self.assertFalse(self.consumer.has_frame)
        self.assertEqual(self.consumer.frames, {0: frame})
        self.consumer.dll.native_drop_pool.assert_not_called()
        self.released[0] = 6  # Stale completion must not free sequence 7.
        self.consume()
        self.consumer.dll.native_drop_pool.assert_not_called()
        self.released[0] = 7
        self.consume()
        self.consumer.dll.native_drop_pool.assert_called_once()
        self.assertEqual(self.box.state(), RETIRED)
        self.assertEqual(self.consumer.frames, {})

    def test_end_invalidates_frames(self):
        self.consume()
        self.box.publish(TextureFrame(1, 1, 0, 1, 0, 0))
        self.consume()
        self.consumer.end()
        self.assertFalse(self.consumer.has_frame)
        self.assertEqual(self.consumer.frames, {})
        self.consumer.dll.native_end.assert_called_once()


if __name__ == "__main__":
    unittest.main()
