import unittest
from screento3d_app.native_memory_contract import allocation_bytes,MAX_ALLOCATION

class NativeAllocationTests(unittest.TestCase):
    def test_supported_frame_and_history_sizes(self):
        self.assertEqual(allocation_bytes((2160,8192,4),1),70778880)
        self.assertEqual(allocation_bytes((2442*4,31,64),4),77518848)
        self.assertEqual(allocation_bytes((MAX_ALLOCATION//4,),4),MAX_ALLOCATION)
    def test_invalid_and_overflowing_allocations_rejected_before_cuda(self):
        for shape in ((),(0,),(-1,),(True,),(2.5,),(MAX_ALLOCATION,), (2**63,2**63)):
            with self.subTest(shape=shape),self.assertRaises(ValueError):allocation_bytes(shape,4)
