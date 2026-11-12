"""Real OS pipe/cancellation regressions without GPU, codecs or external services."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from depthsbs_app.media_process import MediaProcesses
from depthsbs_app.pipeline import verify_output


class MediaPipeTests(unittest.TestCase):
    def test_stderr_flood_does_not_block_stdout_and_keeps_only_a_bounded_tail(self):
        with MediaProcesses() as job:
            child=job.spawn([sys.executable,'-c',"import sys;sys.stderr.buffer.write(b'A'*300000+b'LAST');sys.stderr.flush();sys.stdout.buffer.write(b'frame');sys.stdout.flush()"],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            rescue=threading.Timer(4,child.kill);rescue.start()
            try:
                self.assertEqual(child.stdout.read(),b'frame')
                self.assertEqual(child.wait(timeout=2),0)
                tail=child.stderr.read()
                self.assertLessEqual(len(tail),65536);self.assertTrue(tail.endswith(b'LAST'))
            finally:rescue.cancel()
        self.assertTrue(child.closed)
        self.assertFalse(child.stderr.thread.is_alive())

    def test_cancel_releases_blocked_raw_read_and_write_and_reaps_only_owned_children(self):
        for direction in ('read','write'):
            with self.subTest(direction=direction),tempfile.TemporaryDirectory() as folder:
                cancel=Path(folder)/'cancel';child=None;started=time.monotonic()
                with self.assertRaises(InterruptedError):
                    with MediaProcesses(cancel) as job:
                        child=job.spawn([sys.executable,'-c',"import sys,time;sys.stdout.write('r');sys.stdout.flush();time.sleep(10)"],
                            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                        self.assertEqual(child.stdout.read(1),b'r')
                        request=threading.Timer(.1,cancel.touch);rescue=threading.Timer(4,child.kill)
                        request.start();rescue.start()
                        try:
                            try:
                                if direction=='read':child.stdout.read(1)
                                else:child.stdin.write(b'x'*(1024*1024))
                            except (BrokenPipeError,OSError):job.check_cancel()
                            job.check_cancel()
                        finally:request.cancel();rescue.cancel()
                self.assertLess(time.monotonic()-started,4)
                self.assertIsNotNone(child.poll());self.assertTrue(child.closed)
                self.assertFalse(child.stderr.thread.is_alive())

    def test_cancel_applies_to_probe_or_mux_commands_while_waiting(self):
        with tempfile.TemporaryDirectory() as folder:
            cancel=Path(folder)/'cancel'
            with self.assertRaises(InterruptedError):
                with MediaProcesses(cancel) as job:
                    timer=threading.Timer(.15,cancel.touch);timer.start()
                    try:job.run([sys.executable,'-c','import time;time.sleep(2)'])
                    finally:timer.cancel()
            self.assertTrue(all(child.closed and child.poll() is not None for child in job.children))

    def test_metadata_overflow_is_rejected_after_child_cleanup(self):
        with self.assertRaises(RuntimeError):
            with MediaProcesses() as job:
                job.run([sys.executable,'-c',"print('x'*(4*1024*1024+1))"])
        self.assertTrue(all(child.closed and child.poll() is not None for child in job.children))


class FinalMediaTests(unittest.TestCase):
    def test_mux_validation_rejects_truncation_wrong_geometry_and_nonfinite_duration(self):
        good=dict(width=320,height=180,nb_frames='48',duration='2.000000')
        for changes in ({},{'nb_frames':'5'},{'width':640},{'duration':'nan'},{'duration':'0.25'},{'nb_frames':'N/A'}):
            with self.subTest(changes=changes):
                stream=dict(good,**changes)
                with patch('depthsbs_app.pipeline._run',return_value=subprocess.CompletedProcess([],0,json.dumps({'streams':[stream]}),'')):
                    if changes:
                        with self.assertRaises(RuntimeError):verify_output(Path('owned.mp4'),48,320,180,24,media=object())
                    else:verify_output(Path('owned.mp4'),48,320,180,24,media=object())


if __name__=='__main__':unittest.main()
