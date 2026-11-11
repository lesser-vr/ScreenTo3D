"""Worker-only host-frame adapter for the existing pinned NVIDIA VFG bridge."""
import ctypes as ct
import os
import threading
import time
import numpy as np
from .messages import ErrorMessage as E


class FileVfg:
    def __init__(self,width,height,*,device=0):
        if not (32<=width<=8192 and 16<=height<=2160):raise ValueError(E('E_FILE_VFG_GEOMETRY'))
        self.owner=threading.get_ident();self.width,self.height=width,height
        self.handle=None;self.stream=None;self.device_buffers=[];self.host_buffers=[]
        self.dll_dirs=[];self.modules=[];self.bridge=None
        self.old_path=os.environ.get('NV_VIDEO_EFFECTS_PATH');self.calls=0;self.elapsed=0.
        try:
            from .vfg_runtime import validate_runtime
            sdk,bridge=validate_runtime()
            for folder in (sdk/'bin',sdk/'features/nvvfxvideoframegeneration/bin'):
                self.dll_dirs.append(os.add_dll_directory(str(folder)))
            os.environ['NV_VIDEO_EFFECTS_PATH']=str(sdk/'bin')
            for name in ('bin/NVVideoEffects.dll','bin/NVCVImage.dll',
                         'features/nvvfxvideoframegeneration/bin/nvVFXVideoFrameGeneration.dll'):
                self.modules.append(ct.WinDLL(str(sdk/name)))
            import torch
            self.torch=torch;self.stream=torch.cuda.Stream(device=device)
            with torch.cuda.device(device),torch.cuda.stream(self.stream):
                self.device_buffers=[torch.empty((height,width,4),dtype=torch.uint8,device=f'cuda:{device}') for _ in range(3)]
                self.host_buffers=[torch.empty((height,width,4),dtype=torch.uint8,pin_memory=True) for _ in range(3)]
                for value in self.host_buffers:value.numpy()[:,:,3]=255
                self.bridge=ct.CDLL(str(bridge));self.bridge.live_texture_error.restype=ct.c_char_p
                self.bridge.vfg_create.argtypes=[ct.c_int,ct.c_int,ct.c_void_p];self.bridge.vfg_create.restype=ct.c_void_p
                self.bridge.vfg_destroy.argtypes=[ct.c_void_p];self.bridge.vfg_run.argtypes=[ct.c_void_p]*4
                self.handle=self.bridge.vfg_create(width,height,self.stream.cuda_stream);self._check(self.handle)
        except BaseException as error:
            try:self.close()
            except Exception:error.add_note('File VFG initialization cleanup failed')
            raise

    def _check(self,result):
        if not result:
            detail=self.bridge.live_texture_error().decode('utf-8','replace')
            raise RuntimeError(E('E_FILE_VFG_FAILED',details=detail))

    def generate(self,previous,current):
        if threading.get_ident()!=self.owner or self.handle is None:raise RuntimeError('Invalid file VFG owner/session')
        for frame in (previous,current):
            if frame.shape!=(self.height,self.width,3) or frame.dtype!=np.uint8:raise ValueError('Invalid file VFG input frame')
        began=time.perf_counter()
        with self.torch.cuda.stream(self.stream):
            for index,frame in enumerate((previous,current)):
                self.host_buffers[index].numpy()[:,:,:3]=frame
                self.device_buffers[index].copy_(self.host_buffers[index],non_blocking=True)
            self._check(self.bridge.vfg_run(self.handle,*(value.data_ptr() for value in self.device_buffers)))
            self.host_buffers[2].copy_(self.device_buffers[2],non_blocking=True)
        self.stream.synchronize()
        result=self.host_buffers[2].numpy()[:,:,:3].copy()
        self.calls+=1;self.elapsed+=time.perf_counter()-began
        return result

    def telemetry(self):
        return dict(engine='nvidia-vfg',mode='medium',calls=self.calls,seconds=self.elapsed,
                    staging='bounded-pinned-host-and-device-rgba',width=self.width,height=self.height)

    def close(self):
        if threading.get_ident()!=self.owner:raise RuntimeError('Foreign file VFG cleanup')
        errors=[]
        if self.handle is not None:
            try:self._check(self.bridge.vfg_destroy(self.handle))
            except Exception as error:errors.append(error)
            self.handle=None
        if self.stream is not None:
            try:self.stream.synchronize()
            except Exception as error:errors.append(error)
        self.device_buffers=[];self.host_buffers=[];self.stream=None
        for directory in reversed(self.dll_dirs):
            try:directory.close()
            except Exception as error:errors.append(error)
        self.dll_dirs=[]
        if self.old_path is None:os.environ.pop('NV_VIDEO_EFFECTS_PATH',None)
        else:os.environ['NV_VIDEO_EFFECTS_PATH']=self.old_path
        self.modules=[];self.bridge=None
        if errors:raise errors[0]

    def __enter__(self):return self

    def __exit__(self,kind,value,traceback):
        try:self.close()
        except Exception:
            if value is None:raise
            value.add_note('File VFG cleanup failed')
        return False
