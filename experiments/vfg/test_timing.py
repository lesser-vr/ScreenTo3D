import unittest
import multiprocessing as mp
from unittest.mock import patch
from timing import Timeline


class TimingTests(unittest.TestCase):
    def test_baseline_preserves_future_compositor_timestamp_and_actual_ready(self):
        from native_path import TimedMailbox
        from depthsbs_app.texture_mailbox import TexturePool, TextureFrame
        box = TimedMailbox.create(mp.get_context('spawn'))
        box.offer(TexturePool(1,1,123,640,180,0,0,(11,12)),session=1,owned_pid=123)
        box.install(1,1)
        ready = 1_000_000_000
        frame = TextureFrame(1,1,0,1,ready+1_000_000,ready-6_000_000)
        with patch('native_path.CTX', None), patch('native_path.time.perf_counter_ns', return_value=ready):
            box.publish(frame)
        self.assertEqual(box.frame_timing(frame), (1,frame.source_ns,frame.source_ns,frame.source_ns,0,1,ready,frame.callback_ns))
        box.release(frame)
        # Reject an implausible lead before altering timing or slot ownership.
        with patch('native_path.CTX', None), patch('native_path.time.perf_counter_ns', return_value=ready):
            with self.assertRaises(ValueError):
                box.publish(TextureFrame(1,1,0,2,ready+100_000_001,ready))
        self.assertEqual(box.frame_timing(frame)[0],1)

    def test_start_pair_and_cut(self):
        t = Timeline()
        self.assertEqual(t.plan(1_000_000_000, 1_020_000_000, True), ((0, 1_020_000_000, 1_000_000_000, 1_000_000_000),))
        pair = t.plan(1_040_000_000, 1_060_000_000, False)
        self.assertEqual(pair, ((1, 1_060_000_000, 1_020_000_000, 1_000_000_000),
                                (0, 1_080_000_000, 1_040_000_000, 1_040_000_000)))
        self.assertEqual(len(t.plan(1_080_000_000, 1_090_000_000, True)), 1)

    def test_gap_duplicate_and_clock_reversal_do_not_interpolate(self):
        for source in (900_000_000, 1_000_000_000, 1_200_000_000):
            t = Timeline(previous_source=1_000_000_000)
            self.assertEqual(len(t.plan(source, 1_300_000_000, False)), 1)

    def test_bounded_due_and_invalid_clock(self):
        t = Timeline(last_due=2_000_000_000)
        with self.assertRaises(RuntimeError):
            t.plan(1_000_000_000, 1_010_000_000, False)
        with self.assertRaises(ValueError):
            Timeline().plan(100_000_011, 10, False)

    def test_future_source_and_midpoint_are_scheduled_without_altering_ready(self):
        from native_path import TimedMailbox
        from depthsbs_app.texture_mailbox import TexturePool, TextureFrame
        timeline=Timeline()
        self.assertEqual(timeline.plan(1_000_000_000,999_000_000,True),
                         ((0,1_000_000_000,1_000_000_000,1_000_000_000),))
        ready=1_001_000_000
        plan=timeline.plan(1_016_000_000,ready,False)
        self.assertEqual(plan,((1,1_016_000_000,1_008_000_000,1_000_000_000),
                               (0,1_024_000_000,1_016_000_000,1_016_000_000)))
        box=TimedMailbox.create(mp.get_context('spawn'))
        box.offer(TexturePool(1,1,123,640,180,0,0,(11,12)),session=1,owned_pid=123)
        box.install(1,1)
        for slot,(kind,due,source,oldest) in enumerate(plan):
            frame=TextureFrame(1,1,slot,slot+1,source,ready-1000)
            box.publish_timed(frame,due,oldest,kind,2,ready)
            record=box.frame_timing(frame)
            self.assertEqual(record[6],ready)
            self.assertGreaterEqual(record[1],max(record[2],record[6]))

    def test_metadata_rejects_overwrite_without_gpu_release(self):
        from native_path import TimedMailbox
        from depthsbs_app.texture_mailbox import TexturePool, TextureFrame
        box = TimedMailbox.create(mp.get_context("spawn"))
        box.offer(TexturePool(1,1,123,640,180,0,0,(11,12)),session=1,owned_pid=123)
        box.install(1,1)
        frame = TextureFrame(1,1,0,1,100,110)
        box.publish_timed(frame,130,90,1,1,120)
        before = box.frame_timing(frame)
        with self.assertRaises(ValueError):
            box.publish_timed(TextureFrame(1,1,0,2,120,125),150,100,0,2,140)
        self.assertEqual(box.frame_timing(frame),before)
        # Simulates the acknowledgment AFTER native GPU ownership was returned.
        box.release(frame)
        second = TextureFrame(1,1,0,2,120,125)
        box.publish_timed(second,150,120,0,2,140)
        with self.assertRaises(RuntimeError):
            box.frame_timing(frame)
        self.assertEqual(box.frame_timing(second)[4],0)


if __name__ == "__main__":
    unittest.main()
