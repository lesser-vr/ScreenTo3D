"""Worker-only CUDA memory; bounded pools and explicit stream/device ownership."""
import ctypes as ct
from dataclasses import dataclass
import hashlib
from math import prod
import threading
import weakref

import numpy as np
from .trt_backend import cudart,_cuda
from .portable_cuda import DIRECTORY,PINS
from .native_memory_contract import allocation_bytes

MAX_POOL_BYTES=512*1024**2

@dataclass(frozen=True)
class Device:
    index: int
    type: str='cuda'

class Stream:
    native=True
    def __init__(self,device=None,handle=None):
        self.device=Device(int(_cuda(cudart.cudaGetDevice())) if device is None else device)
        self.thread=threading.get_ident();self.owned=handle is None;self.closed=False
        self.cuda_stream=int(_cuda(cudart.cudaStreamCreate())) if handle is None else int(handle)
    def check(self):
        if self.closed or self.thread!=threading.get_ident() or int(_cuda(cudart.cudaGetDevice()))!=self.device.index:
            raise RuntimeError('Closed or foreign CUDA stream')
    def synchronize(self):self.check();_cuda(cudart.cudaStreamSynchronize(self.cuda_stream))
    def __int__(self):self.check();return self.cuda_stream
    def close(self):
        if self.closed:return
        self.check();self.synchronize();handle=self.cuda_stream;self.closed=True
        if self.owned:_cuda(cudart.cudaStreamDestroy(handle))

class Buffer:
    def __init__(self,arena,shape,dtype,*,pinned=False):
        arena.check();self.arena=arena;self.shape=tuple(shape);self.dtype=np.dtype(dtype);self.pinned=pinned
        if self.dtype not in (np.dtype('uint8'),np.dtype('float32'),np.dtype('int32'),np.dtype('uint64')):
            raise ValueError('Unsupported CUDA buffer dtype')
        self.nbytes=allocation_bytes(self.shape,self.dtype.itemsize);self.ndim=len(shape);self.device=Device(arena.device)
        self.pointer=arena.acquire(self.nbytes,pinned);arena.live.add(self)
    def data_ptr(self):
        self.arena.check()
        if not self.pointer:raise RuntimeError('Expired CUDA buffer')
        return self.pointer
    def numel(self):return prod(self.shape)
    def element_size(self):return self.dtype.itemsize
    def is_contiguous(self):self.data_ptr();return True
    def stride(self,axis):return prod(self.shape[axis+1:])
    def numpy(self):
        if not self.pinned:raise ValueError('Only pinned host storage exposes a NumPy view')
        return np.ctypeslib.as_array((ct.c_ubyte*self.nbytes).from_address(self.data_ptr())).view(self.dtype).reshape(self.shape)
    def upload(self,host):
        host=np.ascontiguousarray(host)
        if host.dtype!=self.dtype or host.shape!=self.shape:raise ValueError('CUDA upload shape/dtype mismatch')
        _cuda(cudart.cudaMemcpyAsync(self.data_ptr(),host.ctypes.data,self.nbytes,cudart.cudaMemcpyKind.cudaMemcpyHostToDevice,int(self.arena.stream)))
        # Pageable source ownership ends here; no outstanding host pointer.
        self.arena.stream.synchronize();return self
    def download(self):
        host=np.empty(self.shape,self.dtype)
        _cuda(cudart.cudaMemcpyAsync(host.ctypes.data,self.data_ptr(),self.nbytes,cudart.cudaMemcpyKind.cudaMemcpyDeviceToHost,int(self.arena.stream)))
        self.arena.stream.synchronize();return host
    def zero(self):
        _cuda(cudart.cudaMemsetAsync(self.data_ptr(),0,self.nbytes,int(self.arena.stream)));return self
    def close(self):
        if self.pointer:
            self.arena.check();pointer,self.pointer=self.pointer,0
            self.arena.release(pointer,self.nbytes,self.pinned)
    def __del__(self):
        if getattr(self,'pointer',0) and not self.arena.closed:
            try:self.close()
            except Exception as error:
                if self.arena.failure is None:self.arena.failure=error.with_traceback(None)

class Arena:
    native=True
    def __init__(self,stream,check=None):
        self.stream=stream;self.device=stream.device.index;self.owner_check=check
        self.closed=False;self.failure=None;self.live=weakref.WeakSet();self.allocations={};self.pool={};self.pool_bytes=0;self.peak=0
        self._dll=None;self.flag=None
    def check(self):
        if self.closed:raise RuntimeError('CUDA arena is closed')
        if self.failure is not None:raise RuntimeError('CUDA arena cleanup failed; restart the session') from self.failure
        self.stream.check()
        if self.owner_check:self.owner_check()
    def acquire(self,size,pinned):
        key=(size,pinned);pool=self.pool.get(key,[])
        if pool:self.pool_bytes-=size;return pool.pop()
        pointer=int(_cuda(cudart.cudaMallocHost(size) if pinned else cudart.cudaMalloc(size)))
        self.allocations[pointer]=key;self.peak=max(self.peak,sum(n for n,_ in self.allocations.values()));return pointer
    def release(self,pointer,size,pinned):
        # Reuse is on this arena's single stream. Cross-stream borrowing is not supported.
        if self.pool_bytes+size<=MAX_POOL_BYTES:
            self.pool.setdefault((size,pinned),[]).append(pointer);self.pool_bytes+=size
        else:
            self.stream.synchronize();self.allocations.pop(pointer)
            _cuda(cudart.cudaFreeHost(pointer) if pinned else cudart.cudaFree(pointer))
    def empty(self,shape,dtype=np.float32,*,pinned=False):return Buffer(self,tuple(shape),dtype,pinned=pinned)
    def from_numpy(self,array):return self.empty(array.shape,array.dtype).upload(array)
    @property
    def dll(self):
        self.check()
        if self._dll is None:
            path=DIRECTORY/'native_memory.dll'
            if hashlib.sha256(path.read_bytes()).hexdigest()!=PINS[path.name]:raise ValueError('CUDA memory utility checksum mismatch')
            dll=ct.CDLL(str(path))
            for name,args in {
                'memory_color':[ct.c_void_p]*2+[ct.c_int]*2+[ct.c_void_p],
                'memory_finite':[ct.c_void_p,ct.c_size_t,ct.c_void_p,ct.c_void_p],
                'memory_equal':[ct.c_void_p]*2+[ct.c_size_t]+[ct.c_void_p]*2,
                'memory_resize':[ct.c_void_p]+[ct.c_int]*3+[ct.c_void_p]+[ct.c_int]*2+[ct.c_void_p],
                'memory_cache':[ct.c_void_p]*2+[ct.c_int]*2+[ct.c_void_p],
            }.items():getattr(dll,name).argtypes=args
            self._dll=dll
        return self._dll
    @staticmethod
    def result(code):
        if code:raise RuntimeError(f'CUDA memory kernel failed: {code}')
    def scalar_flag(self):
        if self.flag is None:self.flag=self.empty((1,),np.int32)
        self.flag.zero();return self.flag
    def finite(self,buffers):
        flag=self.scalar_flag()
        for value in buffers:
            if value.dtype!=np.float32:raise ValueError('Finite validation requires FP32')
            self.result(self.dll.memory_finite(value.data_ptr(),value.numel(),flag.data_ptr(),int(self.stream)))
        return not bool(flag.download()[0])
    def equal(self,a,b):
        if a.shape!=b.shape or a.dtype!=b.dtype:return False
        flag=self.scalar_flag();self.result(self.dll.memory_equal(a.data_ptr(),b.data_ptr(),a.nbytes,flag.data_ptr(),int(self.stream)))
        return not bool(flag.download()[0])
    def resize(self,source,rect,height,width,output=None):
        y,x,h,w=rect;pitch=source.shape[-1]
        if not (0<=y and 0<=x and 1<=h<=source.shape[-2]-y and 1<=w<=pitch-x):raise ValueError('Invalid depth crop')
        output=output or self.empty((1,height,width))
        if output.shape!=(1,height,width) or output.dtype!=np.float32 or source.dtype!=np.float32:raise ValueError('Invalid depth resize storage')
        self.result(self.dll.memory_resize(source.data_ptr()+4*(y*pitch+x),pitch,h,w,output.data_ptr(),height,width,int(self.stream)))
        return output
    def close(self):
        if self.closed:return
        self.stream.check();errors=[] if self.failure is None else [self.failure]
        try:self.stream.synchronize()
        except Exception as exc:errors.append(exc)
        for buffer in list(self.live):buffer.pointer=0
        self.closed=True;self.flag=None
        for pointer,(_,pinned) in list(self.allocations.items()):
            self.allocations.pop(pointer)
            try:_cuda(cudart.cudaFreeHost(pointer) if pinned else cudart.cudaFree(pointer))
            except Exception as exc:errors.append(exc)
        self.pool.clear();self.pool_bytes=0
        if errors:raise ExceptionGroup('CUDA arena cleanup failed',errors)
