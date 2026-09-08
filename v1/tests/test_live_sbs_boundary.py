import multiprocessing as mp
import unittest

from depthsbs_app.live_sbs import reset_reason, validate_strength
from depthsbs_app.capture_mailbox import Mailbox, MAX_BYTES


class LiveSbsBoundaryTests(unittest.TestCase):
    def test_resets(self):
        shape = (720, 480)
        self.assertEqual(reset_reason(None, 1, None, shape, False), "start")
        self.assertEqual(reset_reason(1, 3, shape, shape, False), "gap")
        self.assertEqual(reset_reason(1, 2, shape, (600, 420), False), "resize")
        self.assertEqual(reset_reason(1, 2, shape, shape, True), "cut")
        self.assertIsNone(reset_reason(1, 2, shape, shape, False))

    def test_strength_boundary(self):
        for value in (0, -1, 2.1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                validate_strength(value)
        self.assertEqual(validate_strength(1.25), 1.25)

    def test_full_sbs_slot_capacity(self):
        mailbox = Mailbox.create(mp.get_context("spawn"), sbs=True)
        self.assertEqual(len(mailbox.pixels), MAX_BYTES * 2)

    def test_native_output_has_no_shared_color_buffer(self):
        mailbox = Mailbox.create(mp.get_context("spawn"), sbs=True, metadata_only=True)
        self.assertIsNone(mailbox.pixels)
        self.assertEqual(len(mailbox.meta), 12)


if __name__ == "__main__":
    unittest.main()
