"""Source-only Small prototype: CUDA-owned buffers, no Torch import or emulation."""
import ctypes as ct
import hashlib
from pathlib import Path
import threading
import time

import numpy as np
from depthsbs_app.trt_backend import DepthEngine,_cuda,cudart
from depthsbs_app.gpu_frame import GpuFrame
from depthsbs_app.live_gpu_candidate import LiveGpuCandidate
from depthsbs_app.live_gpu_texture import TextureOutputMixin
from depthsbs_app.small_gpu_input import cubic_coefficients,DLL_PATH,DLL_SHA256
from depthsbs_app.capture_sources import enable_capture_dpi,validate_source
from depthsbs_app.gpu_capture import DLL_PATH as CAPTURE_DLL,DLL_SHA256 as CAPTURE_SHA

ROOT=Path(__file__).resolve().parents[2]
UTILITY=ROOT/'out/native-gpu-runtime/native_rgb.dll'
UTILITY_SHA='ee96ffe58d518f4af56f6c9c9392dffdd50a4fd90701be1bc8d4c94221b49935'


class Owner(DepthEngine):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.device=int(_cuda(cudart.cudaGetDevice()))
    def _check(self):self._device_check()


class Buffer:
    def __init__(self,owner,shape,dtype=np.uint8):
        self.owner=owner;self.thread=threading.get_ident();self.shape=tuple(shape);self.dtype=np.dtype(dtype)
        self.nbytes=int(np.prod(self.shape))*self.dtype.itemsize
        if not 0<self.nbytes<=4096*2160*4:raise ValueError('Unbounded prototype allocation')
        owner._check();self.pointer=int(_cuda(cudart.cudaMalloc(self.nbytes)))
    def data_ptr(self):
        if self.thread!=threading.get_ident() or not self.pointer:raise RuntimeError('Expired or foreign CUDA buffer')
        self.owner._check();return self.pointer
    def is_contiguous(self):self.data_ptr();return True
    def upload(self,host):
        host=np.ascontiguousarray(host)
        if host.shape!=self.shape or host.dtype!=self.dtype:raise ValueError('Unexpected upload geometry')
        _cuda(cudart.cudaMemcpyAsync(self.data_ptr(),host.ctypes.data,self.nbytes,cudart.cudaMemcpyKind.cudaMemcpyHostToDevice,self.owner.stream))
        _cuda(cudart.cudaStreamSynchronize(self.owner.stream))
    def download(self):
        result=np.empty(self.shape,self.dtype)
        _cuda(cudart.cudaMemcpyAsync(result.ctypes.data,self.data_ptr(),self.nbytes,cudart.cudaMemcpyKind.cudaMemcpyDeviceToHost,self.owner.stream))
        _cuda(cudart.cudaStreamSynchronize(self.owner.stream));return result
    def close(self):
        if self.pointer:
            self.data_ptr();_cuda(cudart.cudaStreamSynchronize(self.owner.stream))
            pointer,self.pointer=self.pointer,0;_cuda(cudart.cudaFree(pointer))


class Frame(GpuFrame):
    def __init__(self,owner,rgb,renderer,generation):
        self.engine=owner;self.rgb=rgb;self.renderer=renderer;self.generation=generation
        self.shape=rgb.shape;self.nbytes=rgb.nbytes;self.readback_bytes=self.readback_syncs=0
        self._thumbnail=self._border=self._host=None
    def validate(self,engine):
        self.rgb.data_ptr()
        if engine is not self.engine or self.renderer.generation!=self.generation:raise RuntimeError('Expired native frame')
    def thumbnail(self):
        self.validate(self.engine)
        if self._thumbnail is None:
            self.renderer.check(self.renderer.dll.base_thumbnail(self.rgb.data_ptr(),self.shape[1],self.shape[0],self.renderer.thumbnail_buffer.data_ptr(),int(self.engine.stream)))
            self._thumbnail=self.renderer.thumbnail_buffer.download();self.readback_bytes+=self._thumbnail.nbytes;self.readback_syncs+=1
        return self._thumbnail
    def border(self):
        self.validate(self.engine)
        if self._border is None:
            h,w,_=self.shape;result=np.empty((2*w+2*h,3),np.uint8);p=result.ctypes.data;src=self.rgb.data_ptr();kind=cudart.cudaMemcpyKind.cudaMemcpyDeviceToHost
            _cuda(cudart.cudaMemcpyAsync(p,src,w*3,kind,self.engine.stream))
            _cuda(cudart.cudaMemcpyAsync(p+w*3,src+(h-1)*w*3,w*3,kind,self.engine.stream))
            _cuda(cudart.cudaMemcpy2DAsync(p+2*w*3,3,src,w*3,3,h,kind,self.engine.stream))
            _cuda(cudart.cudaMemcpy2DAsync(p+(2*w+h)*3,3,src+(w-1)*3,w*3,3,h,kind,self.engine.stream))
            _cuda(cudart.cudaStreamSynchronize(self.engine.stream));self._border=result
            self.readback_bytes+=result.nbytes;self.readback_syncs+=1
        return self._border
    def to_host(self):
        self.validate(self.engine)
        if self._host is None:self._host=self.rgb.download();self.readback_bytes+=self._host.nbytes;self.readback_syncs+=1
        return self._host
    def same_pixels(self,other):raise NotImplementedError('The prototype does not enable completed-frame reuse')


class Renderer(TextureOutputMixin,LiveGpuCandidate):
    library_path=DLL_PATH;library_sha256=DLL_SHA256;borrowed_layout_sha256=DLL_SHA256
    def __init__(self,width,height,policy,owner):
        self.buffers=[];self.generation=0
        super().__init__(width,height,policy,owner,diagnostic=True)
        try:
            self.dll.small_prepare.argtypes=[ct.c_void_p,ct.c_void_p,ct.c_size_t,ct.c_int,ct.c_int,ct.c_void_p,ct.c_void_p]
            self.dll.live_post_gpu.argtypes=self.dll.live_post.argtypes
            self.dll.base_thumbnail.argtypes=[ct.c_void_p,ct.c_int,ct.c_int,ct.c_void_p,ct.c_void_p]
            self.rgb=self.allocate((height,width,3));self.thumbnail_buffer=self.allocate((32,32,3))
            coefficients=cubic_coefficients(width,height)
            self.coefficients=self.allocate(coefficients.shape,np.float32);self.coefficients.upload(coefficients)
            if hashlib.sha256(UTILITY.read_bytes()).hexdigest()!=UTILITY_SHA:raise ValueError('Prototype utility checksum mismatch')
            self.utility=ct.CDLL(str(UTILITY))
            self.utility.native_bgra_to_rgb.argtypes=[ct.c_void_p,ct.c_size_t,ct.c_void_p,ct.c_int,ct.c_int,ct.c_void_p]
        except BaseException:
            self.close();raise
    def check(self,code):self._check(code)
    def allocate(self,shape,dtype=np.uint8):
        buffer=Buffer(self.engine,shape,dtype);self.buffers.append(buffer);return buffer
    def frame(self,bgra):
        if bgra.shape!=(self.height,self.width,4):raise ValueError('Unexpected source geometry')
        self.generation+=1
        self.check(self.utility.native_bgra_to_rgb(bgra.data_ptr(),self.width*4,self.rgb.data_ptr(),self.width,self.height,int(self.engine.stream)))
        return Frame(self.engine,self.rgb,self,self.generation)
    def infer(self,frame):
        self._owner();frame.validate(self.engine);self.small_rgb=True
        def prepare(pointer,stream):
            if stream!=int(self.engine.stream):raise ValueError('Foreign prototype stream')
            self.check(self.dll.small_prepare(self.handle,frame.rgb.data_ptr(),self.width*3,self.width,self.height,pointer,self.coefficients.data_ptr()))
        return self.engine.infer_prepared_device(prepare)
    def _post(self,frame,depth,aligned,reset):
        frame.validate(self.engine)
        self.check(self.dll.live_post_gpu(self.handle,frame.rgb.data_ptr(),depth.pointer,self.policy.depth_guide_radius,
            self.policy.temporal_alpha,self.policy.temporal_color_threshold,self.policy.temporal_depth_threshold,
            int(reset),aligned.ctypes.data if aligned is not None else None,self.policy.temporal_depth_transition))
    def close(self):
        try:super().close()
        finally:
            for buffer in reversed(self.buffers):buffer.close()
            self.buffers=[]


class Capture:
    def __init__(self,source,owner):
        enable_capture_dpi();validate_source(source)
        self.source=source;self.owner=owner;self.handle=ct.c_void_p();self.buffer=None
        if hashlib.sha256(CAPTURE_DLL.read_bytes()).hexdigest()!=CAPTURE_SHA:raise ValueError('Capture DLL checksum mismatch')
        self.dll=ct.CDLL(str(CAPTURE_DLL))
        self.dll.gpu_capture_create.argtypes=[ct.POINTER(ct.c_void_p),ct.c_uint64,ct.c_int,ct.c_int,ct.c_int]
        self.dll.gpu_capture_acquire.argtypes=[ct.c_void_p,ct.POINTER(ct.c_int64)]
        self.dll.gpu_capture_copy.argtypes=[ct.c_void_p,ct.c_void_p,ct.c_size_t,ct.c_void_p]
        self.dll.gpu_capture_destroy.argtypes=[ct.c_void_p]
        self.check(self.dll.gpu_capture_create(ct.byref(self.handle),source['id'],0,0,owner.device))
    @staticmethod
    def check(result):
        if result<0:raise RuntimeError(f'Prototype WGC capture HRESULT 0x{result&0xffffffff:08X}')
        return result
    def read(self):
        self.owner._check();validate_source(self.source);info=(ct.c_int64*6)()
        if not self.check(self.dll.gpu_capture_acquire(self.handle,info)):return None
        width,height,sequence,source_ns,callback_ns,replaced=info
        shape=(height,width,4)
        if self.buffer is None:self.buffer=Buffer(self.owner,shape)
        if self.buffer.shape!=shape:raise ValueError('Prototype source resize requires a new session')
        self.check(self.dll.gpu_capture_copy(self.handle,self.buffer.data_ptr(),self.buffer.nbytes,int(self.owner.stream)))
        return self.buffer
    def close(self):
        if self.handle.value:
            _cuda(cudart.cudaStreamSynchronize(self.owner.stream));self.check(self.dll.gpu_capture_destroy(self.handle));self.handle=ct.c_void_p()
        if self.buffer:self.buffer.close();self.buffer=None
