import multiprocessing as mp
import os
import unittest
from unittest.mock import Mock, patch

from depthsbs_app.native_delivery import NativeDelivery
from depthsbs_app.presentation_policy import PresentationCadence
from depthsbs_app.texture_mailbox import (
    TextureMailbox,
    TexturePool,
    TextureFrame,
    OFFERED,
    RETIRED,
)


class NativeProtocolTests(unittest.TestCase):
    def test_adaptive_poll_waits_for_deadline_but_not_retained_current_frame(self):
        self.consume()
        frame = TextureFrame(1, 1, 0, 1, 0, 0)
        self.box.publish(frame)
        c = PresentationCadence(60)
        c.next_ns = 20_000_000
        self.assertEqual(self.consumer.next_poll_delay_ns(self.box, c, 1_000_000), 19_000_000)
        self.consume()
        self.assertIsNone(self.consumer.next_poll_delay_ns(self.box, c, 1_000_000))
        self.box.retire(1, 1)
        self.assertEqual(self.consumer.next_poll_delay_ns(self.box, c, 1_000_000), 1_000_000)

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

    def test_capped_publication_one_frame_per_deadline_with_no_catchup(self):
        self.consume()
        first = TextureFrame(1, 1, 0, 1, 0, 0)
        second = TextureFrame(1, 1, 1, 2, 0, 0)
        self.box.publish(first)
        self.box.publish(second)
        c = PresentationCadence(30)
        with patch('depthsbs_app.native_delivery.time.perf_counter_ns', return_value=100):
            self.consumer.consume(self.box, os.getpid(), cadence=c)
            self.assertEqual(self.consumer.last_sequence, 1)
            self.consumer.consume(self.box, os.getpid(), cadence=c)
            self.assertEqual(self.consumer.dll.native_publish.call_count, 1)
        deadline = c.next_ns
        with patch('depthsbs_app.native_delivery.time.perf_counter_ns', return_value=deadline):
            self.consumer.consume(self.box, os.getpid(), cadence=c)
        self.assertEqual(self.consumer.last_sequence, 2)
        self.assertEqual(self.box.pending(1, 1), (second,))
        self.assertEqual(c.next_ns, deadline + c.period_ns)

    def test_retirement_drains_unpublished_slots_before_deadline(self):
        self.consume()
        for slot in range(2):
            self.box.publish(TextureFrame(1, 1, slot, slot + 1, 0, 0))
        c = PresentationCadence(30)
        c.next_ns = 10**18
        self.consumer.consume(self.box, os.getpid(), cadence=c)
        self.consumer.dll.native_publish.assert_not_called()
        self.box.retire(1, 1)
        self.consumer.consume(self.box, os.getpid(), cadence=c)
        self.assertEqual(self.box.state(), RETIRED)
        self.assertEqual(self.consumer.frames, {})
        self.assertEqual(c.next_ns, 10**18)

    def test_unlimited_does_not_delay_ready_slots(self):
        self.consume()
        for slot in range(2):
            self.box.publish(TextureFrame(1, 1, slot, slot + 1, 0, 0))
        c = PresentationCadence()
        with patch('depthsbs_app.native_delivery.time.perf_counter_ns', return_value=100):
            self.consumer.consume(self.box, os.getpid(), cadence=c)
        self.assertEqual(self.consumer.dll.native_publish.call_count, 2)
        self.assertTrue(c.ready(100))

    def test_waiting_for_deadline_still_reports_errors_and_gpu_releases(self):
        self.consume()
        frame = TextureFrame(1, 1, 0, 1, 0, 0)
        self.box.publish(frame)
        self.consume()
        c = PresentationCadence(60)
        c.next_ns = 10**18
        self.released[0] = 1
        self.consumer.consume(self.box, os.getpid(), cadence=c)
        self.assertEqual(self.box.pending(1, 1), ())
        self.consumer.dll.native_error.return_value = b'GPU failure while capped'
        with self.assertRaisesRegex(RuntimeError, 'GPU failure while capped'):
            self.consumer.consume(self.box, os.getpid(), cadence=c)

    def test_retirement_racing_capped_poll_is_deferred_without_early_release(self):
        self.consume()
        self.box.publish(TextureFrame(1, 1, 0, 1, 0, 0))
        c = PresentationCadence(30)
        def retire_while_checking(now):
            self.box.retire(1, 1)
            return False
        c.ready = retire_while_checking
        self.consumer.consume(self.box, os.getpid(), cadence=c)
        self.consumer.dll.native_drop_pool.assert_not_called()
        self.consumer.consume(self.box, os.getpid(), cadence=c)
        self.assertEqual(self.box.state(), RETIRED)


if __name__ == "__main__":
    unittest.main()
