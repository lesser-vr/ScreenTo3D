import ctypes as ct
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import cv2
import numpy as np

from screento3d_app.flat_background_gpu import FlatBackground, color_bounds
from screento3d_app.live_gpu_candidate import LiveGpuCandidate
from screento3d_app.stereo import uniform_color_mask


class FlatBackgroundGpuTests(unittest.TestCase):
    def test_byte_bounds_match_original_float_predicate(self):
        rgb=np.arange(256,dtype=np.uint8).repeat(3).reshape(16,16,3)
        for color in (np.array([0,32.5,255],np.float32), np.array([15.5,90,170.5],np.float32)):
            for tolerance in (0,.04,.1):
                bounds=color_bounds(color,tolerance)
                expected=uniform_color_mask(rgb,color,tolerance)
                if bounds is None:self.assertFalse(expected.any());continue
                lo,hi=(np.array([(value>>(8*c))&255 for c in range(3)]) for value in bounds)
                np.testing.assert_array_equal(((rgb>=lo)&(rgb<=hi)).all(axis=2),expected)

    def workspace(self, result):
        value=FlatBackground.__new__(FlatBackground)
        value.thread=threading.get_ident();value.failed=False;value.handle=ct.c_void_p(1)
        def apply(*args):
            ct.cast(args[-1],ct.POINTER(ct.c_int))[0]=result
            return 0
        value.dll=SimpleNamespace(flat_apply=Mock(side_effect=apply),flat_destroy=Mock(return_value=0))
        return value

    def test_bypasses_and_applied_result_count_small_reads(self):
        for state,applied,copies,syncs in ((0,False,4,1),(-1,False,12,2),(1,True,12,3)):
            value=self.workspace(state)
            self.assertEqual(value.apply(ct.c_void_p(2),(0,100),.35,8),applied)
            self.assertEqual((value.readback_bytes,value.syncs),(copies,syncs))
            value.close();value.close();value.dll.flat_destroy.assert_called_once()
            with self.assertRaises(RuntimeError):value.apply(None,(0,1),.35,8)

    def test_failure_poison_and_foreign_owner_fail_before_submission(self):
        value=self.workspace(1);value.dll.flat_apply.return_value=0
        value.thread=-1
        with self.assertRaises(RuntimeError):value.apply(None,(0,1),.35,8)
        value.dll.flat_apply.assert_not_called()
        value.thread=threading.get_ident();value.dll.flat_apply.side_effect=None;value.dll.flat_apply.return_value=999
        with self.assertRaises(RuntimeError):value.apply(None,(0,1),.35,8)
        self.assertTrue(value.failed)
        value.close()

    def test_background_close_failure_still_releases_live_and_motion(self):
        value=LiveGpuCandidate.__new__(LiveGpuCandidate)
        value.thread=threading.get_ident();value.failed=False
        value.flat_background=SimpleNamespace(close=Mock(side_effect=RuntimeError('background close')))
        motion=SimpleNamespace(close=Mock());value.motion_history=motion
        value.handle=ct.c_void_p(1);value.dll=SimpleNamespace(live_destroy=Mock(return_value=0))
        value.scene_history=SimpleNamespace(reset=Mock())
        with self.assertRaisesRegex(RuntimeError,'background close'):value.close()
        motion.close.assert_called_once();value.dll.live_destroy.assert_called_once()
        self.assertFalse(value.handle.value)


if __name__=='__main__':unittest.main()
