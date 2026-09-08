"""Development-only TensorRT VDA binding; fixed shape/local validated plans."""
import gc
import hashlib
import os
import sys
import threading
import cv2
import numpy as np
import torch
from torchvision.transforms import Compose
from vda_streaming_experiment import ROOT, upstream_class

PLAN_ROOT=ROOT/'out/vda-trt-parity/87c1b4d53eae42ad9092960883c7fc23'
HASHES={'warmup':'8aa281bd25310b90d959fc0749f7405eae082bd676c1a6f0f5c23b186f4c7690',
        'cached':'6211346dbeab57e98e9bf4238540eecdd72197f1ebe2ffe3ac31167db9cabb33'}


class TensorRTVdaEngine:
    def __init__(self, progress=None):
        self.owner=threading.get_ident(); self.closed=False
        self.engines={}; self.history=[]; self.stream=self.runtime=self.dll=None
        self.shape=None; self.calls=self.resets=self.peak=0
        if not torch.cuda.is_available(): raise RuntimeError('CUDA required; no fallback')
        self.device=torch.cuda.current_device()
        try:
            upstream_class()  # Verify pinned source before importing transforms.
            from video_depth_anything.util.transform import Resize, NormalizeImage, PrepareForNet
            self.transform=Compose([Resize(518,518,resize_target=False,keep_aspect_ratio=True,
                ensure_multiple_of=14,resize_method='lower_bound',image_interpolation_method=cv2.INTER_CUBIC),
                NormalizeImage(mean=[.485,.456,.406],std=[.229,.224,.225]),PrepareForNet()])
            self.dll=os.add_dll_directory('C:/TensorRT/TensorRT-11.2.1.2/bin')
            sys.path.append(str(ROOT/'out/v1-python-deps'))
            import tensorrt as trt
            self.trt=trt
            if trt.__version__!='11.2.1.2' or torch.cuda.get_device_capability()!=(12,0):
                raise RuntimeError('Local validated plan environment mismatch')
            self.logger=trt.Logger(trt.Logger.WARNING); self.runtime=trt.Runtime(self.logger)
            self.stream=torch.cuda.Stream(device=self.device)
            for name,digest in HASHES.items():
                payload=(PLAN_ROOT/f'{name}.plan').read_bytes()
                if hashlib.sha256(payload).hexdigest()!=digest: raise RuntimeError('Plan digest mismatch')
                engine=self.runtime.deserialize_cuda_engine(payload)
                if engine is None: raise RuntimeError('Plan load failed')
                context=engine.create_execution_context()
                if context is None: raise RuntimeError('Context creation failed')
                self.engines[name]=(engine,context)
        except BaseException as primary:
            try: self.close()
            except Exception as error: primary.add_note(str(error))
            raise

    def _check(self):
        if threading.get_ident()!=self.owner: raise RuntimeError('Wrong owner thread')
        if self.closed: raise RuntimeError('VDA TRT closed')
        if torch.cuda.current_device()!=self.device: raise RuntimeError('CUDA device changed')

    def reset(self,reason):
        self._check()
        if reason not in ('start','scene_cut','source_change','discontinuity'): raise ValueError('Unknown reset')
        self.stream.synchronize(); self.history.clear(); self.shape=None; self.resets+=1

    def _execute(self,image):
        warmup=not self.history
        engine,context=self.engines['warmup' if warmup else 'cached']
        inputs={'image':image}
        if not warmup:
            selected=self.history[:2]+self.history[-29:]
            inputs.update({f'cache_{i}':torch.cat([entry[i] for entry in selected],dim=1).contiguous() for i in range(8)})
        outputs={}
        for i in range(engine.num_io_tensors):
            name=engine.get_tensor_name(i)
            if engine.get_tensor_dtype(name)!=self.trt.float32: raise RuntimeError('Unexpected dtype')
            if engine.get_tensor_mode(name)==self.trt.TensorIOMode.INPUT: tensor=inputs[name]
            else:
                tensor=torch.empty(tuple(engine.get_tensor_shape(name)),device=image.device,dtype=torch.float32)
                outputs[name]=tensor
            if tuple(tensor.shape)!=tuple(engine.get_tensor_shape(name)): raise ValueError('Engine shape mismatch')
            if not context.set_tensor_address(name,tensor.data_ptr()): raise RuntimeError('Binding failed')
        if not context.execute_async_v3(self.stream.cuda_stream): raise RuntimeError('TRT execution failed')
        self.stream.synchronize()  # Keep all bound inputs alive until completion.
        if not all(torch.isfinite(value).all().item() for value in outputs.values()):
            raise RuntimeError('Nonfinite TRT depth/cache')
        cache=tuple(outputs[f'new_cache_{i}'] for i in range(8))
        self.history=[cache]*32 if warmup else self.history+[cache]
        if len(self.history)>42: del self.history[1]
        self.peak=max(self.peak,len(self.history))
        return outputs['depth']

    def infer(self,frame):
        self._check()
        if not isinstance(frame,np.ndarray) or frame.dtype!=np.uint8 or frame.ndim!=3 or frame.shape[2]!=3:
            raise ValueError('Expected uint8 RGB')
        if not all(16<=v<=1920 for v in frame.shape[:2]): raise ValueError('Unsupported source size')
        if self.shape is not None and self.shape!=frame.shape: raise ValueError('Reset before source change')
        ratio=max(frame.shape[:2])/min(frame.shape[:2])
        if ratio>1.78: raise ValueError('Aspect ratio outside fixed experiment')
        chw=self.transform({'image':frame.astype(np.float32)/255})['image']
        if chw.shape!=(3,518,896): raise ValueError('Fixed 518x896 experiment only')
        try:
            with torch.no_grad(),torch.cuda.stream(self.stream):
                image=torch.from_numpy(chw.copy())[None,None].to(f'cuda:{self.device}')
                depth=self._execute(image)
                resized=torch.nn.functional.interpolate(depth.flatten(0,1).unsqueeze(1),
                    size=frame.shape[:2],mode='bilinear',align_corners=True)
                result=resized[0].cpu().numpy().copy()
            self.calls+=1; self.shape=frame.shape
            return result
        except BaseException as primary:
            try: self.close()
            except Exception as error: primary.add_note(str(error))
            raise

    def telemetry(self):
        self._check()
        return dict(completed_inferences=self.calls,resets=self.resets,cache_entries=len(self.history),
            peak_cache_entries=self.peak,cache_entry_limit=42,zero_copy=False,
            runtime='TensorRT FP32; torch CUDA buffers',input_shape=[1,1,3,518,896],plan_hashes=HASHES)

    def close(self):
        if threading.get_ident()!=self.owner: raise RuntimeError('Wrong close thread')
        if self.closed: return
        self.closed=True
        try:
            if self.stream is not None: self.stream.synchronize()
        finally:
            self.history.clear(); self.engines.clear(); self.runtime=None; self.stream=None
            gc.collect()
            if self.dll is not None: self.dll.close(); self.dll=None

    def __enter__(self): self._check(); return self
    def __exit__(self,kind,value,tb):
        try: self.close()
        except Exception as error:
            if value is None: raise
            value.add_note(str(error))
        return False


def binding(factory=TensorRTVdaEngine):
    from depthsbs_app.depth_backend import BackendBinding,BackendSpec
    return BackendBinding(BackendSpec('vda-small-trt-experimental','tensorrt',stateful=True,requires_every_frame=True),factory,lambda frame:frame)
