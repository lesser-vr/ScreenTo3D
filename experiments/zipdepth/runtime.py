"""Isolated, pinned RTX 5090 ZipDepth engine for the shared native SBS path."""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import threading

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / 'out/zipdepth-exact-20261106'
PLAN_SHA = '5f618e6e52c0545e950d597e38b38e5ed4926df5fa633b0ebb8aa7b02542450f'
SHAPE = (384, 704)

def rect(width, height):
    if not (16 <= width <= 4096 and 16 <= height <= 2160):
        raise ValueError('Unsupported source dimensions')
    s = min(SHAPE[0]/height, SHAPE[1]/width)
    h, w = max(1, round(height*s)), max(1, round(width*s))
    return (SHAPE[0]-h)//2, (SHAPE[1]-w)//2, h, w

def check_plan():
    payload = (ARTIFACTS/'model.plan').read_bytes()
    if hashlib.sha256(payload).hexdigest() != PLAN_SHA:
        raise ValueError('ZipDepth local plan integrity mismatch')
    report = json.loads((ARTIFACTS/'prepare.json').read_text())
    if not report['completed'] or not report['parity_pass']:
        raise ValueError('ZipDepth parity has not passed')
    return payload

@dataclass(frozen=True)
class DeviceDepth:
    owner: object
    generation: int
    tensor: object
    stream: int
    resources: tuple

    @property
    def pointer(self):
        return self.tensor.data_ptr()

    def validate(self):
        e = self.owner
        e._check()
        if (e.current_device is not self or self.generation != e.device_generation or
            self.stream != e.stream.cuda_stream or self.tensor.dtype != e.torch.float32 or
            tuple(self.tensor.shape) != (1,*e.source_shape) or not self.tensor.is_contiguous() or
            self.tensor.device.index != e.device):
            raise ValueError('Invalid or expired ZipDepth result')

class Engine:
    def __init__(self, progress=None):
        import torch
        self.torch, self.owner = torch, threading.get_ident()
        self.closed = False
        self.dll = self.runtime = self.engine = self.context = self.stream = None
        self.output = self.gpu_input = self.pending_device = self.current_device = None
        self.device = torch.cuda.current_device()
        self.calls = self.device_generation = self.input_upload_bytes = 0
        self.last_input_bytes = 0
        self.profile = self.shape = SHAPE
        self.source_shape = None
        try:
            if torch.cuda.get_device_name() != 'NVIDIA GeForce RTX 5090':
                raise ValueError('This local engine requires RTX 5090')
            payload = check_plan()
            self.dll = os.add_dll_directory('C:/TensorRT/TensorRT-11.2.1.2/bin')
            import tensorrt as trt
            if trt.__version__ != '11.2.1.2':
                raise ValueError('TensorRT version mismatch')
            self.logger = trt.Logger(trt.Logger.WARNING)
            self.runtime = trt.Runtime(self.logger)
            self.engine = self.runtime.deserialize_cuda_engine(payload)
            if self.engine is None or self.engine.num_io_tensors != 2:
                raise ValueError('Invalid engine')
            for name, shape, mode in [('image',(1,3,*SHAPE),trt.TensorIOMode.INPUT),
                                      ('depth',(1,1,*SHAPE),trt.TensorIOMode.OUTPUT)]:
                if (tuple(self.engine.get_tensor_shape(name)) != shape or
                    self.engine.get_tensor_dtype(name) != trt.float32 or
                    self.engine.get_tensor_mode(name) != mode):
                    raise ValueError('Invalid engine tensor contract')
            self.context = self.engine.create_execution_context()
            if self.context is None:
                raise RuntimeError('Context creation failed')
            self.stream = torch.cuda.Stream(device=self.device)
            self.output = torch.empty((1,1,*SHAPE),device=f'cuda:{self.device}')
            from depthsbs_app.gpu_runtime import GpuInputSupport
            from depthsbs_app.base_gpu_input import DLL_PATH, DLL_SHA256
            # Reuse only the model-independent thumbnail kernel/stream support.
            self.gpu_input = GpuInputSupport(self,DLL_PATH,DLL_SHA256,stream=self.stream)
        except BaseException:
            self.close(); raise

    def _check(self):
        if threading.get_ident() != self.owner or self.closed:
            raise RuntimeError('Engine is closed or used from another thread')
        if self.torch.cuda.current_device() != self.device:
            raise RuntimeError('CUDA device changed')

    def infer_device(self, frame):
        from depthsbs_app.gpu_frame import GpuFrame
        import numpy as np
        self._check()
        if self.pending_device is not None:
            raise RuntimeError('Complete pending result first')
        if isinstance(frame,GpuFrame):
            frame.validate(self)
        elif not isinstance(frame,np.ndarray) or frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError('Expected uint8 RGB')
        y,x,h,w = rect(frame.shape[1],frame.shape[0])
        t = self.torch
        try:
            with t.inference_mode(), t.cuda.stream(self.stream):
                rgb = frame.rgb if isinstance(frame,GpuFrame) else t.from_numpy(np.ascontiguousarray(frame)).to(f'cuda:{self.device}')
                self.last_input_bytes = 0 if isinstance(frame,GpuFrame) else frame.nbytes
                self.input_upload_bytes += self.last_input_bytes
                # Quantized bilinear resize mirrors the reference uint8 operation.
                image = t.nn.functional.interpolate(rgb.permute(2,0,1)[None].float(), (h,w), mode='bilinear', align_corners=False)
                image = image.round().clamp(0,255).div_(255)
                image = t.nn.functional.pad(image,(x,SHAPE[1]-w-x,y,SHAPE[0]-h-y),mode='replicate').contiguous()
                if not (self.context.set_tensor_address('image',image.data_ptr()) and self.context.set_tensor_address('depth',self.output.data_ptr())):
                    raise RuntimeError('Tensor binding failed')
                if not self.context.execute_async_v3(self.stream.cuda_stream):
                    raise RuntimeError('Inference failed')
                resized = t.nn.functional.interpolate(self.output[:,:,y:y+h,x:x+w], frame.shape[:2],mode='bilinear',align_corners=True)[:,0].contiguous()
                if not bool(t.isfinite(resized).all()):
                    raise ValueError('Nonfinite depth')
            self.calls += 1
            self.device_generation += 1
            self.source_shape = tuple(frame.shape[:2])
            result = DeviceDepth(self,self.device_generation,resized,self.stream.cuda_stream,(rgb,image,self.output))
            self.pending_device = self.current_device = result
            result.validate()
            return result
        except BaseException:
            self.close(); raise

    def complete_device(self, token):
        if token.owner is not self:
            raise ValueError('Foreign result')
        token.validate()
        self.stream.synchronize()
        # Completion releases the in-flight inference, not the cached result.
        # Performance mode reuses it for exact-equal RGB until the next inference.
        self.pending_device = None

    def telemetry(self):
        self._check()
        return dict(model_id='zipdepth-base',runtime='tensorrt-fp16',plan_sha256=PLAN_SHA,
                    input_shape=[1,3,*SHAPE], completed_inferences=self.calls,
                    host_to_device_bytes=self.input_upload_bytes,device_depth_output=True,
                    pending_device_depth=self.pending_device is not None,
                    cuda_peak_allocated_bytes=self.torch.cuda.max_memory_allocated(),
                    memory_scope='Torch allocator only; excludes TensorRT/D3D allocations')

    def close(self):
        if threading.get_ident() != self.owner:
            raise RuntimeError('Close on owner thread')
        if self.closed:
            return
        if self.stream is not None:
            self.stream.synchronize()
        self.pending_device = self.current_device = self.output = self.gpu_input = self.context = self.engine = self.runtime = self.stream = None
        if self.dll is not None:
            self.dll.close(); self.dll = None
        self.closed = True

    def __enter__(self):
        self._check(); return self

    def __exit__(self,*args):
        self.close()
