"""TensorRT Base/VDA bindings with CUDA-owned buffers and unchanged model history."""
from dataclasses import dataclass
import hashlib
import os
import threading
import time

import numpy as np
from .cuda_memory import Stream,Arena,cudart,_cuda
from .engine_cache import device_identity
from .resources import prepare_dll_search_path
from .gpu_frame import GpuFrame

@dataclass(frozen=True)
class DeviceDepth:
    owner: object
    generation: int
    tensor: object
    stream: int
    @property
    def pointer(self):self.validate();return self.tensor.data_ptr()
    @property
    def shape(self):return self.tensor.shape
    def validate(self):
        self.owner._check()
        if (self.owner.pending_device is not self or self.generation!=self.owner.device_generation
                or self.tensor.dtype!=np.float32 or self.stream!=int(self.owner.stream)):
            raise RuntimeError('Expired or foreign native device depth')
        self.tensor.data_ptr()

class NativeEngine:
    native=True
    def initialize(self,runtime):
        self.owner=threading.get_ident();self.closed=False;self.stream=self.memory=self.dll=self.runtime=None
        self.device=int(_cuda(cudart.cudaGetDevice()));self.engines={}
        self.pending_device=None;self.device_generation=0;self.device_submissions=self.device_completions=0
        self.calls=self.upload_bytes=self.download_bytes=0;self.preprocess_seconds=0.
        self.shape=None;self.resized=None;self._gpu_input=None
        self.last_input_bytes=0;self.history=[];self.free_banks=[];self.resets=self.peak=0
        try:
            if device_identity(self.device)!=device_identity():raise RuntimeError('Engine GPU identity differs from the installed device')
            self.dll=prepare_dll_search_path(runtime)
            import tensorrt as trt
            self.trt=trt
            if trt.__version__!='11.2.1.2':raise RuntimeError('TensorRT version mismatch')
            self.runtime=trt.Runtime(trt.Logger(trt.Logger.WARNING))
            self.stream=Stream(self.device);self.memory=Arena(self.stream,self._check)
        except BaseException:self.close();raise
    def _check(self):
        if self.closed or self.owner!=threading.get_ident():raise RuntimeError('Closed or foreign native engine')
        if int(_cuda(cudart.cudaGetDevice()))!=self.device:raise RuntimeError('Native engine CUDA device changed')
    def load(self,name,payload,expected):
        engine=self.runtime.deserialize_cuda_engine(payload)
        if engine is None:raise RuntimeError('TensorRT deserialization failed')
        self.engines[name]=(engine,None)
        actual={engine.get_tensor_name(i) for i in range(engine.num_io_tensors)}
        if actual!=set(expected):raise ValueError('TensorRT tensor names/count mismatch')
        for key,(shape,is_input) in expected.items():
            if (tuple(engine.get_tensor_shape(key))!=tuple(shape) or engine.get_tensor_dtype(key)!=self.trt.float32
                    or (engine.get_tensor_mode(key)==self.trt.TensorIOMode.INPUT)!=is_input):
                raise ValueError(f'TensorRT tensor signature mismatch: {key}')
        ctx=engine.create_execution_context()
        if ctx is None:raise RuntimeError('TensorRT context creation failed')
        self.engines[name]=(engine,ctx)
    def submit(self,name,buffers):
        _,ctx=self.engines[name]
        for key,value in buffers.items():
            if not ctx.set_tensor_address(key,value.data_ptr()):raise RuntimeError('TensorRT buffer binding failed')
        if not ctx.execute_async_v3(int(self.stream)):raise RuntimeError('TensorRT inference submission failed')
    def resized_depth(self,raw,frame):
        h,w=frame.shape[:2]
        if self.resized is None or self.resized.shape!=(1,h,w):
            if self.resized is not None:self.resized.close()
            self.resized=self.memory.empty((1,h,w))
        return self.memory.resize(raw,self.content_rect(w,h,self.canvas),h,w,self.resized)
    def _infer(self,frame,device):
        self._check()
        if self.pending_device is not None:raise RuntimeError('Complete device depth before another inference')
        if not isinstance(frame,(GpuFrame,np.ndarray)) or frame.dtype!=np.uint8 or frame.ndim!=3 or frame.shape[2]!=3:
            raise ValueError('Expected uint8 RGB frame')
        self.content_rect(frame.shape[1],frame.shape[0],self.canvas)
        if self.model=='vda-small' and self.shape is not None and self.shape!=frame.shape:raise ValueError('Reset VDA before source shape changes')
        try:
            started=time.perf_counter()
            if isinstance(frame,GpuFrame):
                frame.validate(self)
                if self.model=='da2-base' and self.input_path!='gpu':raise ValueError('GPU capture requires GPU preprocessing')
                if self.model=='vda-small':self.gpu_input.prepare(frame.rgb,self.canvas,self.model_input)
                else:self.gpu_input.prepare(frame.rgb,self.model_input)
                self.last_input_bytes=0
            elif device and self.model=='da2-base' and self.input_path=='gpu':
                rgb=self.memory.from_numpy(frame)
                self.gpu_input.prepare(rgb,self.model_input);self.last_input_bytes=frame.nbytes
                rgb.close()
            else:
                chw=self.preprocess(frame,self.canvas)
                self.model_input.upload(chw.reshape(self.model_input.shape));self.last_input_bytes=chw.nbytes
            self.preprocess_seconds+=time.perf_counter()-started;self.upload_bytes+=self.last_input_bytes
            raw=self.execute()
            result=self.resized_depth(raw,frame)
            if not self.memory.finite([result]):raise ValueError('Nonfinite native source depth')
            self.calls+=1
            if self.model=='vda-small':self.shape=frame.shape
            if device:
                self.device_generation+=1;self.device_submissions+=1
                token=DeviceDepth(self,self.device_generation,result,int(self.stream));self.pending_device=token
                token.validate();return token
            output=result.download();self.download_bytes+=output.nbytes;return output
        except BaseException as primary:
            try:self.close()
            except Exception as cleanup:primary.add_note(str(cleanup))
            raise
    def infer(self,frame):return self._infer(frame,False)
    def infer_device(self,frame):return self._infer(frame,True)
    def complete_device(self,token):
        if token.owner is not self:raise ValueError('Foreign depth owner')
        token.validate();self.stream.synchronize();self.pending_device=None;self.device_completions+=1
    def reset(self,reason):
        self._check()
        if self.pending_device is not None:raise RuntimeError('Complete device depth before reset')
        if reason not in ('start','scene_cut','source_change','discontinuity'):raise ValueError('Invalid depth reset')
        self.stream.synchronize()
        self.free_banks.extend({id(bank):bank for bank in self.history}.values());self.history=[]
        self.shape=None;self.device_generation+=1;self.resets+=1
    def telemetry(self):
        self._check()
        result=dict(model_id=self.model,completed_inferences=self.calls,resets=self.resets,
            runtime=f"TensorRT {getattr(self,'manifest',{}).get('precision','mixed-fp16')}; native CUDA buffers",buffer_backend='native-cuda',input_shape=list(self.input_shape),
            host_to_device_bytes=self.upload_bytes,device_to_host_bytes=self.download_bytes,
            preprocessing_ms=1000*self.preprocess_seconds,cache_entries=len(self.history),peak_cache_entries=self.peak,
            cache_entry_limit=42,cuda_allocated_bytes=sum(n for n,pinned in self.memory.allocations.values() if not pinned),
            cuda_peak_allocated_bytes=self.memory.peak,memory_scope='owned CUDA arena; TensorRT allocations excluded',
            device_depth_submissions=self.device_submissions,device_depth_completions=self.device_completions,
            pending_device_depth=self.pending_device is not None,zero_copy=False)
        if self.model=='da2-base':result.update(plan_sha256=self.plan_hash,weight_license='CC-BY-NC-4.0',io_precision='fp32',input_preprocessing=self.input_path,cuda_graph=False)
        else:result['plan_hashes']={key:value['sha256'] for key,value in self.manifest['engines'].items()}
        return result
    def close(self):
        if self.owner!=threading.get_ident():raise RuntimeError('Foreign native engine cleanup')
        if self.closed:return
        errors=[]
        if self.memory:
            try:self.memory.close()
            except Exception as exc:errors.append(exc)
        self.pending_device=None;self.history=[];self.free_banks=[];self.engines.clear();self.runtime=None;self._gpu_input=None
        if self.stream:
            try:self.stream.close()
            except Exception as exc:errors.append(exc)
        if self.dll:
            try:self.dll.close()
            except Exception as exc:errors.append(exc)
        self.closed=True;self.device_generation+=1
        if errors:raise ExceptionGroup('Native engine cleanup failed',errors)
    def __enter__(self):self._check();return self
    def __exit__(self,kind,primary,tb):
        try:self.close()
        except Exception as exc:
            if primary is None:raise
            primary.add_note(str(exc))

from .environment import get as app_env

class NativeBaseEngine(NativeEngine):
    model='da2-base'
    def __init__(self,directory,runtime,shape=(518,896),*,device_depth=False):
        from .da2_base import checked_plan,content_rect,preprocess
        from .engine_cache import local_record
        self.input_path=app_env('SCREENTO3D_BASE_INPUT','gpu')
        if self.input_path not in ('cpu','gpu'):raise ValueError('SCREENTO3D_BASE_INPUT must be cpu or gpu')
        if app_env('SCREENTO3D_BASE_GRAPH','0')!='0' or app_env('SCREENTO3D_BASE_STAGE_PROFILE','0')!='0':
            raise ValueError('Native CUDA buffers do not support the source-only Torch graph/stage diagnostic; clear its environment override')
        self.canvas=tuple(shape);self.profile=self.canvas;self.input_shape=(1,3,*shape)
        self.content_rect=content_rect;self.preprocess=preprocess
        payload=checked_plan(directory,shape);record=local_record(directory,'da2-base');identity=device_identity()
        expected=(record['gpu'],record['compute_capability']) if record else ('NVIDIA GeForce RTX 5090',[12,0])
        if (identity['gpu'],identity['compute_capability'])!=expected:raise RuntimeError('Base engine GPU mismatch')
        self.initialize(runtime)
        self.shape=self.canvas
        try:
            self.load('model',payload,{'image':(self.input_shape,True),'depth':((1,*shape),False)})
            self.model_input=self.memory.empty(self.input_shape);self.depth=self.memory.empty((1,*shape))
            self.plan_hash=hashlib.sha256(payload).hexdigest()
        except BaseException:self.close();raise
    @property
    def gpu_input(self):
        if self._gpu_input is None:
            from .base_gpu_input import BaseGpuInput
            self._gpu_input=BaseGpuInput(self)
        return self._gpu_input
    def execute(self):
        self.submit('model',{'image':self.model_input,'depth':self.depth});return self.depth

class NativeVdaEngine(NativeEngine):
    model='vda-small'
    def __init__(self,directory,runtime,progress=None):
        from .vda_artifacts import load_manifest,cache_layout,content_rect
        from .vda_preprocess import preprocess
        from pathlib import Path
        self.manifest=load_manifest(directory);self.input_shape=tuple(self.manifest['input_shape']);self.canvas=self.input_shape[-2:]
        if self.manifest['tensorrt']!='11.2.1.2':raise RuntimeError('VDA TensorRT version mismatch')
        self.content_rect=content_rect;self.preprocess=preprocess;self.layout=cache_layout(self.canvas)
        identity=device_identity()
        if identity['gpu']!=self.manifest['gpu'] or identity['compute_capability']!=self.manifest['compute_capability']:
            raise RuntimeError('VDA engine GPU mismatch')
        self.initialize(runtime)
        try:
            for stage in ('warmup','cached'):
                record=self.manifest['engines'][stage];payload=(Path(directory)/record['file']).read_bytes()
                if hashlib.sha256(payload).hexdigest()!=record['sha256']:raise ValueError('VDA engine checksum mismatch')
                expected={'image':(self.input_shape,True),'depth':((1,1,*self.canvas),False)}
                for i,(spatial,channels) in enumerate(self.layout):
                    expected[f'new_cache_{i}']=((spatial,1,channels),False)
                    if stage=='cached':expected[f'cache_{i}']=((spatial,31,channels),True)
                self.load(stage,payload,expected)
            self.model_input=self.memory.empty((1,3,*self.canvas))
            self.depth=self.memory.empty((1,1,*self.canvas))
            self.cache_inputs=[self.memory.empty((spatial,31,channels)) for spatial,channels in self.layout]
            self.cache_pointers=self.memory.empty((8,31),np.uint64)
        except BaseException:self.close();raise
    @property
    def gpu_input(self):
        if self._gpu_input is None:
            from .gpu_runtime import FixedCanvasGpuInput
            from .portable_cuda import DIRECTORY,PINS
            self._gpu_input=FixedCanvasGpuInput(self,DIRECTORY/'vda_input.dll',PINS['vda_input.dll'],'vda_prepare',self.content_rect)
        return self._gpu_input
    def execute(self):
        warmup=not self.history;buffers={'image':self.model_input,'depth':self.depth}
        if not warmup:
            selected=self.history[:2]+self.history[-29:]
            if len(selected)!=31:raise RuntimeError('Invalid native VDA cache schedule')
            # History banks are private to this already-checked owner/stream.
            # Validate their liveness once without 248 redundant CUDA device queries.
            pointers=np.array([[bank[i].pointer for bank in selected] for i in range(8)],np.uint64)
            if not pointers.all():raise RuntimeError('Expired VDA cache bank')
            self.cache_pointers.upload(pointers)
            for i,(spatial,channels) in enumerate(self.layout):
                self.memory.result(self.memory.dll.memory_cache(self.cache_pointers.data_ptr()+i*31*8,self.cache_inputs[i].data_ptr(),spatial,channels,int(self.stream)))
                buffers[f'cache_{i}']=self.cache_inputs[i]
        bank=self.free_banks.pop() if self.free_banks else tuple(self.memory.empty((s,1,c)) for s,c in self.layout)
        buffers.update({f'new_cache_{i}':value for i,value in enumerate(bank)})
        self.submit('warmup' if warmup else 'cached',buffers)
        if not self.memory.finite([self.depth,*bank]):raise RuntimeError('VDA produced nonfinite depth/cache')
        self.history=[bank]*32 if warmup else self.history+[bank]
        if len(self.history)>42:
            retired=self.history.pop(1)
            if all(retired is not retained for retained in self.history):self.free_banks.append(retired)
        self.peak=max(self.peak,len(self.history));return self.depth
