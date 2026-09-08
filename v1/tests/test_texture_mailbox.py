import ctypes
from dataclasses import replace
import multiprocessing as mp
import os
import time
import unittest

from depthsbs_app.texture_mailbox import (
    TexturePool,
    TextureFrame,
    TextureMailbox,
    WORD_COUNT,
    INSTALLED,
    CLOSED,
)


def _spawn_offer(box, connection):
    """Real spawned ownership identity; dummy handles, no GPU/import claim."""
    try:
        pool = TexturePool(1, 1, os.getpid(), 640, 180, 23, -1, (100, 104))
        box.offer(pool, session=1, owned_pid=os.getpid())
        connection.send(os.getpid())
        if connection.poll(5) and connection.recv() == "installed":
            box.publish(TextureFrame(1, 1, 0, 1, 1000, 1100))
            connection.send("published")
    finally:
        connection.close()


class TextureMailboxTests(unittest.TestCase):
    def setUp(self):
        self.context = mp.get_context("spawn")
        self.box = TextureMailbox.create(self.context)
        self.pool = TexturePool(1, 1, os.getpid(), 640, 180, 23, -1, (100, 104))

    def offer(self, pool=None):
        self.box.offer(pool or self.pool, session=1, owned_pid=os.getpid())

    def install(self):
        self.offer()
        self.box.install(1, 1)

    def frame(self, slot=0, sequence=1):
        return TextureFrame(1, 1, slot, sequence, 1000, 1100)

    def test_fixed_metadata_without_pixel_allocation(self):
        self.assertEqual(ctypes.sizeof(self.box.words), WORD_COUNT * 8)
        self.assertEqual(len(self.box.words), 19)
        self.assertFalse(hasattr(self.box, "pixels"))

    def test_descriptor_roundtrip_and_installation_gate(self):
        self.offer()
        self.assertEqual(self.box.offered(session=1, owned_pid=os.getpid()), self.pool)
        self.assertEqual(self.box.writable_slots(1, 1), ())
        with self.assertRaises(RuntimeError):
            self.box.publish(self.frame())
        self.box.install(1, 1)
        self.assertEqual(self.box.state(), INSTALLED)
        self.assertIsNone(self.box.offered(session=1, owned_pid=os.getpid()))
        self.assertEqual(self.box.writable_slots(1, 1), (0, 1))

    def test_reject_unowned_pool_before_handle_import(self):
        self.offer()
        for session, pid in ((2, os.getpid()), (1, os.getpid() + 1)):
            with self.assertRaises(ValueError):
                self.box.offered(session=session, owned_pid=pid)

    def test_descriptor_ranges_and_types(self):
        cases = dict(
            session=[0, True, 2**63],
            generation=[0, -1],
            origin_pid=[0, 2**32],
            width=[31, 33, 8194, 640.0],
            height=[15, 2161],
            luid_low=[-1, 2**32],
            luid_high=[-(2**31) - 1, 2**31],
            handles=[(0, 4), (4, 4), (True, 4), (2**63, 4), [4, 8], (4,)],
        )
        for field, values in cases.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValueError):
                        self.offer(replace(self.pool, **{field: value}))

    def test_both_slots_survive_a_missed_poll_in_frame_order(self):
        self.install()
        first, second = self.frame(1, 1), self.frame(0, 2)
        self.box.publish(first)
        self.box.publish(second)
        self.assertEqual(self.box.pending(1, 1), (first, second))
        self.assertEqual(self.box.pending(1, 1), (first, second))
        self.assertEqual(self.box.writable_slots(1, 1), ())
        with self.assertRaises(RuntimeError):
            self.box.publish(self.frame(1, 3))
        self.box.release(first)
        self.assertEqual(self.box.pending(1, 1), (second,))
        self.assertEqual(self.box.writable_slots(1, 1), (1,))
        self.box.publish(self.frame(1, 3))
        self.assertEqual(len(self.box.pending(1, 1)), 2)

    def test_stale_duplicate_release_cannot_unlock_new_frame(self):
        self.install()
        first = self.frame()
        self.box.publish(first)
        self.box.release(first)
        with self.assertRaises(ValueError):
            self.box.release(first)
        self.box.publish(self.frame(0, 2))
        with self.assertRaises(ValueError):
            self.box.release(first)
        self.assertEqual(self.box.pending(1, 1), (self.frame(0, 2),))

    def test_monotonic_frame_ids_across_slots(self):
        self.install()
        self.box.publish(self.frame(0, 2))
        for sequence in (1, 2):
            with self.assertRaises(ValueError):
                self.box.publish(self.frame(1, sequence))

    def test_frame_range_validation(self):
        self.install()
        for field, values in dict(
            slot=[-1, 2, True],
            sequence=[0, 2**63, True],
            source_ns=[-1, 2**63],
            callback_ns=[-1, 2**63],
        ).items():
            for value in values:
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValueError):
                        self.box.publish(replace(self.frame(), **{field: value}))

    def test_live_pool_cannot_be_replaced(self):
        self.install()
        with self.assertRaises(RuntimeError):
            self.offer(replace(self.pool, generation=2))

    def test_retirement_waits_for_both_releases(self):
        self.install()
        for frame in (self.frame(), self.frame(1, 2)):
            self.box.publish(frame)
        self.box.retire(1, 1)
        self.assertEqual(self.box.writable_slots(1, 1), ())
        self.box.release(self.frame())
        with self.assertRaises(RuntimeError):
            self.box.finish_retirement(1, 1)
        self.box.release(self.frame(1, 2))
        self.box.finish_retirement(1, 1)
        self.offer(replace(self.pool, generation=2, width=800))
        self.box.install(1, 2)
        with self.assertRaises(ValueError):
            self.box.publish(replace(self.frame(), generation=2, sequence=2))
        self.box.publish(replace(self.frame(), generation=2, sequence=3))
        with self.assertRaises(ValueError):
            self.box.release(self.frame())

    def test_cancel_offer_before_installation(self):
        self.offer()
        self.box.retire(1, 1)
        with self.assertRaises(RuntimeError):
            self.box.install(1, 1)
        self.box.finish_retirement(1, 1)
        with self.assertRaises(ValueError):
            self.offer()
        with self.assertRaises(ValueError):
            self.box.offer(
                replace(self.pool, session=2), session=2, owned_pid=os.getpid()
            )

    def test_close_is_terminal_and_not_a_release(self):
        self.install()
        self.box.publish(self.frame())
        self.box.close()
        self.assertEqual(self.box.state(), CLOSED)
        self.assertEqual(self.box.pending(1, 1), ())
        with self.assertRaises(RuntimeError):
            self.box.release(self.frame())
        with self.assertRaises(RuntimeError):
            self.offer(replace(self.pool, generation=2))

    def test_stale_session_operations_fail(self):
        self.install()
        for method in (
            self.box.install,
            self.box.pending,
            self.box.retire,
            self.box.finish_retirement,
            self.box.writable_slots,
        ):
            with self.subTest(method=method.__name__):
                with self.assertRaises(ValueError):
                    method(2, 1)

    def test_busy_lock_fails_bounded_without_mutation(self):
        with self.box.lock:
            start = time.monotonic()
            with self.assertRaises(TimeoutError):
                self.offer()
            self.assertLess(time.monotonic() - start, 1)
        self.offer()

    def test_spawned_transport_and_actual_owned_pid(self):
        parent, child = self.context.Pipe()
        process = self.context.Process(target=_spawn_offer, args=(self.box, child))
        process.start()
        child.close()
        try:
            self.assertTrue(parent.poll(10))
            self.assertEqual(parent.recv(), process.pid)
            pool = self.box.offered(session=1, owned_pid=process.pid)
            self.assertEqual(pool.origin_pid, process.pid)
            self.box.install(1, 1)
            parent.send("installed")
            self.assertTrue(parent.poll(10))
            self.assertEqual(parent.recv(), "published")
            self.assertEqual(self.box.pending(1, 1), (self.frame(),))
            self.box.release(self.frame())
            process.join(5)
            self.assertEqual(process.exitcode, 0)
        finally:
            parent.close()
            if process.is_alive():
                process.terminate()
                process.join(5)
            process.close()


if __name__ == "__main__":
    unittest.main()
