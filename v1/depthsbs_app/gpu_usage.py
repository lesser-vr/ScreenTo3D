"""Optional device-wide NVIDIA utilization; bounded polling, no CLI or GPU work."""
import ctypes as ct
import os
from pathlib import Path
from uuid import UUID

POLL_NS = 1_000_000_000
MAX_AGE_NS = 3_000_000_000


class Utilization(ct.Structure):
    _fields_ = [('gpu', ct.c_uint), ('memory', ct.c_uint)]


class NvmlUsage:
    def __init__(self, uuid, library=None):
        self.library = library if library is not None else ct.CDLL(
            str(Path(os.environ['SystemRoot']) / 'System32/nvml.dll'))
        self.initialized = False
        lib = self.library
        lib.nvmlInit_v2.argtypes = []
        lib.nvmlInit_v2.restype = ct.c_int
        lib.nvmlShutdown.argtypes = []
        lib.nvmlShutdown.restype = ct.c_int
        lib.nvmlDeviceGetHandleByUUID.argtypes = [ct.c_char_p, ct.POINTER(ct.c_void_p)]
        lib.nvmlDeviceGetHandleByUUID.restype = ct.c_int
        lib.nvmlDeviceGetUtilizationRates.argtypes = [ct.c_void_p, ct.POINTER(Utilization)]
        lib.nvmlDeviceGetUtilizationRates.restype = ct.c_int
        if lib.nvmlInit_v2():
            raise RuntimeError('NVML utilization unavailable')
        self.initialized = True
        try:
            self.handle = ct.c_void_p()
            name = ('GPU-' + str(UUID(hex=uuid))).encode('ascii')
            if lib.nvmlDeviceGetHandleByUUID(name, ct.byref(self.handle)):
                raise RuntimeError('Processing GPU utilization unavailable')
        except Exception:
            self.close()
            raise

    def read(self):
        values = Utilization()
        if not self.initialized or self.library.nvmlDeviceGetUtilizationRates(self.handle, ct.byref(values)):
            raise RuntimeError('GPU utilization unavailable')
        if values.gpu > 100:
            raise ValueError('Invalid GPU utilization')
        return int(values.gpu)

    def close(self):
        if self.initialized:
            self.initialized = False
            self.library.nvmlShutdown()


class UsageSampler:
    def __init__(self, reader=None):
        self.reader = reader
        self.next_ns = 0

    @classmethod
    def current_cuda(cls):
        # Only the worker calls this after its engine selected the active CUDA
        # device. UUID mapping avoids assuming NVML index 0 matches CUDA index 0.
        try:
            from .trt_backend import cudart, _cuda
            from .engine_cache import device_identity
            identity = device_identity(_cuda(cudart.cudaGetDevice()))
            return cls(NvmlUsage(identity['uuid']))
        except Exception:
            return cls()

    def poll(self, now_ns):
        if now_ns < self.next_ns:
            return None
        self.next_ns = now_ns + POLL_NS
        value = -1
        if self.reader is not None:
            try:
                value = self.reader.read()
                if type(value) is not int or not 0 <= value <= 100:
                    value = -1
            except Exception:
                pass
        return value, now_ns

    def close(self):
        reader, self.reader = self.reader, None
        if reader is not None:
            try:
                reader.close()
            except Exception:
                pass  # Optional telemetry must not fail session cleanup.


def usage_text(value, sample_ns, now_ns, *, active):
    if active and 0 <= value <= 100 and sample_ns > 0 and 0 <= now_ns - sample_ns <= MAX_AGE_NS:
        return f'GPU {value}%'
    return 'GPU —'
