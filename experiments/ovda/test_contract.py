# NC-SA-UHDV1.0; see accompanying LICENSE.
import unittest
import numpy as np
from oracle import schedule, validate_frame


class ContractTests(unittest.TestCase):
    def test_schedule(self):
        for capacity in (8,16):
            for used in range(capacity):
                mask,position = schedule(used,capacity)
                self.assertEqual(len(mask),capacity-1)
                self.assertEqual(position,[0,1] if used==0 else [used,used])
                self.assertTrue(all(0 <= v < capacity for v in mask+position))
                self.assertEqual(set(mask),set(range(max(1,used),capacity)))

    def test_invalid_schedule(self):
        for used in (-1,16,True,1.5):
            with self.assertRaises(ValueError): schedule(used)

    def test_frame(self):
        for h,w in ((608,1056),(720,1280),(1080,1920),(2160,3840),(720,960)):
            validate_frame(np.zeros((h,w,3),np.uint8))
        for frame in (np.zeros((720,1280,3),np.float32),np.zeros((1280,720,3),np.uint8),
                      np.zeros((2161,3840,3),np.uint8),np.zeros((720,1280),np.uint8)):
            with self.assertRaises(ValueError): validate_frame(frame)


if __name__ == '__main__': unittest.main()
