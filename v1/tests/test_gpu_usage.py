import ctypes as ct
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from depthsbs_app.gpu_usage import NvmlUsage,UsageSampler,Utilization,usage_text


class GpuUsageTests(unittest.TestCase):
    def library(self):
        return SimpleNamespace(**{name:Mock(return_value=0) for name in (
            'nvmlInit_v2','nvmlShutdown','nvmlDeviceGetHandleByUUID','nvmlDeviceGetUtilizationRates')})

    def test_selects_uuid_and_reports_actual_zero_utilization(self):
        lib=self.library()
        def read(handle,result):
            ct.cast(result,ct.POINTER(Utilization)).contents.gpu=0
            return 0
        lib.nvmlDeviceGetUtilizationRates.side_effect=read
        usage=NvmlUsage('00112233445566778899aabbccddeeff',lib)
        self.assertEqual(lib.nvmlDeviceGetHandleByUUID.call_args.args[0],b'GPU-00112233-4455-6677-8899-aabbccddeeff')
        self.assertEqual(usage.read(),0)
        usage.close();usage.close()
        lib.nvmlShutdown.assert_called_once()

    def test_failed_device_binding_shuts_down_initialized_library(self):
        lib=self.library();lib.nvmlDeviceGetHandleByUUID.return_value=6
        with self.assertRaises(RuntimeError):NvmlUsage('00112233445566778899aabbccddeeff',lib)
        lib.nvmlShutdown.assert_called_once()

    def test_sampler_is_bounded_and_invalidates_failed_samples(self):
        reader=Mock();reader.read.side_effect=[65,RuntimeError('unavailable'),0]
        sampler=UsageSampler(reader)
        self.assertEqual(sampler.poll(1),(65,1))
        for i in range(2,1000):self.assertIsNone(sampler.poll(i))
        self.assertEqual(reader.read.call_count,1)
        self.assertEqual(sampler.poll(1_000_000_001),(-1,1_000_000_001))
        self.assertEqual(sampler.poll(2_000_000_001),(0,2_000_000_001))
        sampler.close();sampler.close();reader.close.assert_called_once()

    def test_unavailable_init_or_bad_values_do_not_look_like_zero(self):
        self.assertEqual(UsageSampler().poll(1),(-1,1))
        for value in (True,101,-5,float('nan')):
            self.assertEqual(UsageSampler(Mock(read=Mock(return_value=value))).poll(1),(-1,1))

    def test_display_rejects_stale_future_inactive_or_missing_samples(self):
        self.assertEqual(usage_text(65,1,1_000_000_001,active=True),'GPU 65%')
        self.assertEqual(usage_text(0,1,1,active=True),'GPU 0%')
        for value,stamp,now,active in ((65,1,3_000_000_002,True),(65,2,1,True),
                                       (-1,1,1,True),(65,0,1,True),(65,1,1,False)):
            self.assertEqual(usage_text(value,stamp,now,active=active),'GPU —')


if __name__=='__main__':unittest.main()
