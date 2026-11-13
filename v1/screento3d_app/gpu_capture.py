"""Owned, bounded WGC/D3D11 CUDA capture. No image readback in this module."""
import ctypes as ct
import hashlib
import threading
import time

from .desktop_jobs import ROOT
from .capture_sources import enable_capture_dpi, validate_source, monitors

DLL_PATH = ROOT / 'out/gpu-capture/gpu_capture.dll'
DLL_SHA256 = 'adebe984ad7b66a35e007a99921e810694b1aa822f08ca0dea17b7afc6326a68'


class GpuCapture:
    def __init__(self, source, cursor, device):
        from .cuda_memory import Stream,Arena
        self.device=device;self.memory=Arena(Stream(device,handle=0));self.image=None
        self.thread = threading.get_ident()
        self.source = dict(source)
        self.handle = ct.c_void_p()
        self.failed = False
        self.last_health = 0
        self.resizes = 0
        self.previous_shape = None
        enable_capture_dpi()
        validate_source(self.source)
        if hashlib.sha256(DLL_PATH.read_bytes()).hexdigest() != DLL_SHA256:
            raise ValueError('GPU capture DLL checksum mismatch')
        self.dll = ct.CDLL(str(DLL_PATH))
        self.dll.gpu_capture_create.argtypes = [ct.POINTER(ct.c_void_p), ct.c_uint64, ct.c_int, ct.c_int, ct.c_int]
        self.dll.gpu_capture_acquire.argtypes = [ct.c_void_p, ct.POINTER(ct.c_int64)]
        self.dll.gpu_capture_copy.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_size_t, ct.c_void_p]
        self.dll.gpu_capture_destroy.argtypes = [ct.c_void_p]
        target = source['id']
        if source['kind'] == 'monitor':
            target = next(r['handle'] for r in monitors() if r['id'] == source['id'] and r['device'] == source['device'])
        self._check(self.dll.gpu_capture_create(ct.byref(self.handle), target, source['kind'] == 'monitor', bool(cursor), device))

    def _owner(self):
        from .cuda_memory import cudart,_cuda
        if threading.get_ident() != self.thread or int(_cuda(cudart.cudaGetDevice())) != self.device:
            raise RuntimeError('GPU capture requires its owner thread/device')

    def _check(self, result):
        if result < 0:
            self.failed = True
            raise RuntimeError(f'GPU capture failed (HRESULT 0x{result & 0xffffffff:08X})')
        return result

    def read(self, stream):
        self._owner()
        if not self.handle.value or self.failed:
            raise RuntimeError('GPU capture is closed or failed')
        if stream.device.index != self.device:
            raise ValueError('Foreign capture CUDA stream')
        if time.monotonic() - self.last_health >= .1:
            validate_source(self.source)
            self.last_health = time.monotonic()
        info = (ct.c_int64 * 6)()
        if not self._check(self.dll.gpu_capture_acquire(self.handle, info)):
            return None
        width, height, sequence, source_ns, callback_ns, replaced = info
        shape = (height, width)
        if self.previous_shape is not None and shape != self.previous_shape:
            self.resizes += 1
        self.previous_shape = shape
        try:
            if getattr(stream,'native',False):
                import numpy as np
                if self.image is None or self.image.shape!=(*shape,4):
                    if self.image is not None:self.image.close()
                    self.image=self.memory.empty((*shape,4),np.uint8)
                image=self.image
                self._check(self.dll.gpu_capture_copy(self.handle, image.data_ptr(), image.numel(), stream.cuda_stream))
            else:
                import torch
                with torch.cuda.stream(stream):
                    image=torch.empty((*shape,4),dtype=torch.uint8,device=f'cuda:{self.device}')
                    self._check(self.dll.gpu_capture_copy(self.handle,image.data_ptr(),image.numel(),stream.cuda_stream))
        except BaseException:
            self.failed = True
            raise
        return image, dict(width=width, height=height, sequence=sequence,
            source_ns=source_ns, callback_ns=callback_ns, replaced=replaced, resizes=self.resizes)

    def close(self):
        self._owner()
        try:
            if self.handle.value:
                self._check(self.dll.gpu_capture_destroy(self.handle))
                self.handle = ct.c_void_p()
        finally:self.memory.close()

    def __enter__(self):
        return self

    def __exit__(self, kind, primary, tb):
        try:
            self.close()
        except Exception as error:
            if primary is None:
                raise
            primary.add_note(str(error))
