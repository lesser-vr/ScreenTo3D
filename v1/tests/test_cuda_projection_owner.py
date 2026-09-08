import ctypes
import unittest
from unittest.mock import Mock, patch
import numpy as np
from cuda_projection_experiment import CudaProjection


class OwnerTests(unittest.TestCase):
    def setUp(self):
        self.dll = Mock()
        def create(pointer, width, height):
            pointer._obj.value = 42
            return 0
        self.dll.projection_create.side_effect = create
        self.dll.projection_run.return_value = 0
        self.dll.projection_destroy.return_value = 0
        self.loader = patch('cuda_projection_experiment.ctypes.CDLL', return_value=self.dll)
        self.loader.start()
        self.addCleanup(self.loader.stop)
        self.frame = np.zeros((4, 8, 3), np.uint8)
        self.depth = np.zeros((4, 8), np.float32)

    def owner(self):
        return CudaProjection(8, 4, __file__)

    def test_close_is_idempotent_and_closed_handle_rejected(self):
        owner = self.owner()
        owner.close()
        owner.close()
        self.dll.projection_destroy.assert_called_once()
        with self.assertRaisesRegex(RuntimeError, 'closed'):
            owner.project(self.frame, self.depth, self.depth)

    def test_invalid_arrays_do_not_reach_native_code(self):
        with self.owner() as owner:
            for bad in (np.zeros((4, 8), np.float64), np.full((4, 8), np.nan, np.float32), np.zeros((1, 8), np.float32)):
                with self.assertRaises(ValueError):
                    owner.project(self.frame, bad, self.depth)
        self.dll.projection_run.assert_not_called()

    def test_run_failure_closes_and_preserves_primary_error(self):
        self.dll.projection_run.return_value = 17
        self.dll.projection_destroy.return_value = 23
        owner = self.owner()
        with self.assertRaisesRegex(RuntimeError, 'run failed: 17') as caught:
            owner.project(self.frame, self.depth, self.depth)
        self.assertIn('23', caught.exception.__notes__[0])
        owner.close()
        self.dll.projection_destroy.assert_called_once()

    def test_scope_exception_preserved_on_cleanup_failure(self):
        self.dll.projection_destroy.return_value = 23
        with self.assertRaisesRegex(ValueError, 'primary') as caught:
            with self.owner():
                raise ValueError('primary')
        self.assertIn('cleanup', caught.exception.__notes__[0])

    def test_wrong_thread_is_rejected_before_native_call(self):
        owner = self.owner()
        original = owner.owner_thread
        owner.owner_thread = -1
        try:
            with self.assertRaisesRegex(RuntimeError, 'owner thread'):
                owner.project(self.frame, self.depth, self.depth)
            with self.assertRaisesRegex(RuntimeError, 'owner thread'):
                owner.close()
        finally:
            owner.owner_thread = original
            owner.close()
        self.dll.projection_run.assert_not_called()
