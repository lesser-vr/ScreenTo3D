# oVDA cache/preprocessing adaptation, NC-SA-UHDV1.0; see LICENSE/README.md.
"""Explicit local c16 mixed-FP16 engine with FP32 I/O/cache; no fallback."""
import os
import threading
import numpy as np
import torch
if __package__:
    from .oracle import ROOT, schedule, REVISION, WEIGHT_HASH
    from .preprocessing import FramePreprocessor, validate_frame
else:
    from oracle import ROOT, schedule, REVISION, WEIGHT_HASH
    from preprocessing import FramePreprocessor, validate_frame

PLAN = ROOT/'out/ovda-local/518x924-fp16/model.plan'


class OvdaTrt:
    def __init__(self, progress=None, directory=None, runtime_dir=None, profile=(518,924)):
        from depthsbs_app.ovda import checked_plan, PROFILES, RUNTIME
        if profile not in PROFILES:raise ValueError('Unvalidated oVDA profile')
        self.profile=profile;self.plan_hash=PROFILES[profile][0]
        self.runtime_label=RUNTIME
        h,w=profile; n=(h//14)*(w//14)
        self.caches={'c1':(n,192),'c2':(((h//14+1)//2)*((w//14+1)//2),384),'c3':(n,64),'c4':(n*4,64)}
        self.owner=threading.get_ident();self.closed=False
        self.device=torch.cuda.current_device() if torch.cuda.is_available() else None
        self.dll=self.engine=self.context=self.runtime=self.stream=self.pre=None
        self.cache={};self.shape=None;self.used=self.calls=self.resets=0
        if self.device is None:raise RuntimeError('oVDA TensorRT requires CUDA')
        try:
            if torch.cuda.get_device_capability()!=(12,0) or 'RTX 5090' not in torch.cuda.get_device_name():
                raise RuntimeError('Only local validated RTX 5090 supported')
            payload=checked_plan(directory if directory is not None else PLAN.parent,profile)
            if torch.__version__!='2.7.1+cu128':raise RuntimeError('oVDA requires validated torch 2.7.1+cu128; use scripts/run-ovda.ps1')
            self.pre=FramePreprocessor(profile)
            self.dll=os.add_dll_directory(str(runtime_dir or 'C:/TensorRT/TensorRT-11.2.1.2/bin'))
            import tensorrt as trt
            if trt.__version__!='11.2.1.2':raise RuntimeError('TensorRT version mismatch')
            self.trt=trt;self.logger=trt.Logger(trt.Logger.WARNING)
            self.runtime=trt.Runtime(self.logger)
            self.engine=self.runtime.deserialize_cuda_engine(payload)
            if self.engine is None:raise RuntimeError('Engine load failed')
            self.signature={'image':((1,1,3,h,w),trt.float32,True),
                'mask':((15,),trt.int64,True),'position':((2,),trt.int64,True),
                'depth':((1,1,h,w),trt.float32,False)}
            for key,(n,c) in self.caches.items():
                self.signature['cache_'+key]=((1,2,n,16,c),trt.float32,True)
                self.signature['new_'+key]=((1,2,n,1,c),trt.float32,False)
            if self.engine.num_io_tensors!=len(self.signature):raise ValueError('Unexpected tensor count')
            for i in range(self.engine.num_io_tensors):
                name=self.engine.get_tensor_name(i)
                if name not in self.signature:raise ValueError('Unexpected tensor name')
                shape,dtype,inp=self.signature[name]
                if (tuple(self.engine.get_tensor_shape(name))!=shape or self.engine.get_tensor_dtype(name)!=dtype
                    or (self.engine.get_tensor_mode(name)==trt.TensorIOMode.INPUT)!=inp):raise ValueError('Unexpected tensor signature')
            self.context=self.engine.create_execution_context()
            if self.context is None:raise RuntimeError('Context creation failed')
            self.stream=torch.cuda.Stream(device=self.device)
        except BaseException:
            self.close();raise

    def check(self):
        if threading.get_ident()!=self.owner:raise RuntimeError('oVDA owner thread changed')
        if self.closed:raise RuntimeError('oVDA TensorRT engine closed')
        if torch.cuda.current_device()!=self.device:raise RuntimeError('CUDA device changed')

    def reset(self,reason):
        self.check()
        if reason not in ('start','scene_cut','source_change','discontinuity'):raise ValueError('Unknown reset reason')
        self.stream.synchronize();self.cache.clear();self.used=0;self.shape=None;self.resets+=1

    def infer(self,frame):
        self.check();validate_frame(frame)
        if self.shape is not None and self.shape!=frame.shape:raise ValueError('Reset before geometry change')
        try:
            with torch.inference_mode(),torch.cuda.stream(self.stream):
                image=self.pre.preprocess(frame.copy()).to(f'cuda:{self.device}').contiguous()
                if not self.cache:
                    self.cache={k:torch.zeros((1,2,n,16,c),device=image.device,dtype=torch.float32) for k,(n,c) in self.caches.items()}
                mask,pos=schedule(self.used)
                inputs={'image':image,'mask':torch.tensor(mask,device=image.device,dtype=torch.int64),
                        'position':torch.tensor(pos,device=image.device,dtype=torch.int64),**{'cache_'+k:v for k,v in self.cache.items()}}
                outputs={}
                for name,(shape,dtype,is_input) in self.signature.items():
                    if is_input:tensor=inputs[name]
                    else:
                        tensor=torch.empty(shape,device=image.device,dtype=torch.float32);outputs[name]=tensor
                    if tuple(tensor.shape)!=shape:raise ValueError('Bound buffer shape mismatch')
                    expected_dtype=torch.float32 if dtype==self.trt.float32 else torch.int64
                    if tensor.dtype!=expected_dtype or not tensor.is_contiguous() or tensor.device!=image.device:
                        raise ValueError('Bound buffer dtype/layout/device mismatch')
                    if not self.context.set_tensor_address(name,tensor.data_ptr()):raise RuntimeError('Binding failed')
                if not self.context.execute_async_v3(self.stream.cuda_stream):raise RuntimeError('Execution failed')
                self.stream.synchronize()  # Own every bound tensor until GPU completion.
                if not all(bool(torch.isfinite(v).all()) for v in outputs.values()):raise ValueError('Nonfinite oVDA output')
                if self.used==15:
                    self.cache={k:torch.cat([v[:,:,:,1:15,:],outputs['new_'+k],torch.zeros_like(outputs['new_'+k])],dim=3)
                                for k,v in self.cache.items()}
                else:
                    for k in self.cache:self.cache[k][:,:,:,self.used,:]=outputs['new_'+k][:,:,:,0,:]
                self.used=min(self.used+1,15)
                result=self.pre.restore_depth(outputs['depth'],frame.shape[:2])
                result=result[:,0].cpu().numpy().astype(np.float32,copy=True)
                self.stream.synchronize()
            if result.shape!=(1,*frame.shape[:2]) or not np.isfinite(result).all():raise ValueError('Invalid resized depth')
            self.calls+=1;self.shape=frame.shape
            return result
        except BaseException as primary:
            try:self.close()
            except Exception as error:primary.add_note(str(error))
            raise

    def telemetry(self):
        self.check()
        return dict(model_id='ovda-small-c16',runtime=self.runtime_label,
            source_revision=REVISION,weight_sha256=WEIGHT_HASH,plan_sha256=self.plan_hash,
            license='NC-SA-UHDV1.0',completed_inferences=self.calls,resets=self.resets,
            cache_slots=16,cache_used=self.used,cache_bytes=sum(v.numel()*v.element_size() for v in self.cache.values()),
            input_shape=[1,1,3,*self.profile],zero_copy=False)

    def close(self):
        if threading.get_ident()!=self.owner:raise RuntimeError('oVDA close requires owner thread')
        if self.closed:return
        try:
            if self.stream is not None:self.stream.synchronize()
        finally:
            self.cache.clear();self.context=self.engine=self.runtime=self.stream=self.pre=None
            if self.dll is not None:self.dll.close();self.dll=None
            self.closed=True

    def __enter__(self):self.check();return self
    def __exit__(self,*exc):self.close()
