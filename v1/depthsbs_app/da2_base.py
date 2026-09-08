"""Explicit local DA2 Base FP32 backend; CC-BY-NC-4.0 weights."""
import hashlib
import os
from pathlib import Path
import threading
import time

import cv2
import numpy as np

PLAN_HASH = '93d5159282cc96ac2ea79895051f7646514791cac9351917c62f444818b78209'
PLAN_BYTES = 402367692
SHAPE = (1, 3, 518, 896)
PROFILES = {
    (518, 896): (PLAN_HASH, PLAN_BYTES),
    (518, 924): ('e5b17445993602abf2a01c0f6e7686d5fa67afec49bd9ef8bb4c133175c89d2e', 402660828),
}


def validate_input(metadata, shape=(518,896)):
    from .vda_artifacts import validate_input as validate_profile
    validate_profile(metadata, shape)


def preprocess(frame, shape=(518,896)):
    if not isinstance(frame, np.ndarray) or frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError('DA2 Base requires uint8 RGB')
    validate_input(dict(width=frame.shape[1], height=frame.shape[0]), shape)
    # DA2 upstream divides uint8 by 255 before resize (float64, unlike VDA).
    image = cv2.resize(frame / 255.0, (shape[1], shape[0]), interpolation=cv2.INTER_CUBIC)
    return np.ascontiguousarray(((image-[.485,.456,.406])/[.229,.224,.225]).transpose(2,0,1), dtype=np.float32)


def checked_plan(directory, shape=(518,896)):
    directory = Path(directory).resolve(strict=True)
    path = (directory/'model.plan').resolve(strict=True)
    expected_hash, expected_bytes = PROFILES[shape]
    if path.parent != directory or path.stat().st_size != expected_bytes:
        raise ValueError('DA2 Base plan path/size mismatch')
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected_hash:
        raise ValueError('DA2 Base plan checksum mismatch; use the validated local build')
    return payload


def profiles(directory):
    directory = Path(directory).resolve(strict=True)
    if (directory/'model.plan').exists():
        size = (directory/'model.plan').stat().st_size
        for shape, (_, count) in PROFILES.items():
            if size == count:
                checked_plan(directory, shape)
                return {shape: directory}
        raise ValueError('Unknown DA2 Base plan size')
    found = {}
    for shape in PROFILES:
        child = directory/f'{shape[0]}x{shape[1]}-fp32'
        if child.exists():
            child = child.resolve(strict=True)
            if child.parent != directory:
                raise ValueError('DA2 Base profile escapes selected directory')
            checked_plan(child, shape)
            found[shape] = child
    if not found:
        raise ValueError('No validated DA2 Base profiles found')
    return found


def binding(directory, runtime_dir):
    from .depth_backend import BackendBinding, BackendSpec
    if directory is None or runtime_dir is None:
        raise ValueError('DA2 Base requires engine and TensorRT runtime directories')
    installed = profiles(directory)
    if not (Path(runtime_dir)/'nvinfer_11.dll').is_file():
        raise ValueError('TensorRT 11 runtime not found')
    selected = next(iter(installed)) if len(installed) == 1 else None
    def validate(metadata):
        nonlocal selected
        from .vda_artifacts import profile_shape
        selected = None
        shape = profile_shape(metadata['width'], metadata['height'])
        if shape not in installed:
            raise ValueError(f'No DA2 Base engine for {shape}; select the matching profile root')
        validate_input(metadata, shape)
        selected = shape
    def factory(progress):
        if selected is None:
            raise ValueError('Select DA2 Base profile with input preflight first')
        if progress:
            progress(dict(event='da2_base_profile', input_shape=[1,3,*selected]))
        return Da2BaseEngine(installed[selected], runtime_dir, selected)
    return BackendBinding(BackendSpec('da2-base', 'tensorrt-fp32'), factory, lambda frame: frame, validate)


class Da2BaseEngine:
    def __init__(self, directory, runtime_dir, shape=(518,896)):
        import torch
        self.torch, self.owner = torch, threading.get_ident()
        self.closed = False
        self.stream = self.runtime = self.engine = self.context = self.dll = self.output = None
        self.calls = 0
        self.preprocess_seconds = 0.
        self.shape = shape
        if not torch.cuda.is_available():
            raise RuntimeError('DA2 Base requires CUDA')
        self.device = torch.cuda.current_device()
        if torch.cuda.get_device_capability() != (12, 0) or torch.cuda.get_device_name() != 'NVIDIA GeForce RTX 5090':
            raise RuntimeError('This DA2 Base build requires RTX 5090')
        payload = checked_plan(directory, shape)
        try:
            self.dll = os.add_dll_directory(str(Path(runtime_dir).resolve(strict=True)))
            import tensorrt as trt
            if trt.__version__ != '11.2.1.2':
                raise RuntimeError('DA2 Base requires TensorRT 11.2.1.2')
            self.logger = trt.Logger(trt.Logger.WARNING)
            self.runtime = trt.Runtime(self.logger)
            self.engine = self.runtime.deserialize_cuda_engine(payload)
            if self.engine is None:
                raise RuntimeError('DA2 Base deserialization failed')
            expected = {'image': ((1,3,*shape), trt.TensorIOMode.INPUT), 'depth': ((1,*shape), trt.TensorIOMode.OUTPUT)}
            if self.engine.num_io_tensors != 2:
                raise ValueError('DA2 Base tensor count mismatch')
            for i in range(2):
                key = self.engine.get_tensor_name(i)
                if (key not in expected or self.engine.get_tensor_dtype(key) != trt.float32 or
                    (tuple(self.engine.get_tensor_shape(key)), self.engine.get_tensor_mode(key)) != expected[key]):
                    raise ValueError('DA2 Base tensor signature mismatch')
            self.context = self.engine.create_execution_context()
            if self.context is None:
                raise RuntimeError('DA2 Base context creation failed')
            self.stream = torch.cuda.Stream(device=self.device)
            self.output = torch.empty((1,*shape), device=f'cuda:{self.device}', dtype=torch.float32)
        except BaseException:
            self.close()
            raise

    def _check(self):
        if threading.get_ident() != self.owner:
            raise RuntimeError('DA2 Base requires its owner thread')
        if self.closed:
            raise RuntimeError('DA2 Base is closed')
        if self.torch.cuda.current_device() != self.device:
            raise RuntimeError('DA2 Base CUDA device changed')

    def infer(self, frame):
        self._check()
        start = time.perf_counter()
        chw = preprocess(frame, self.shape)
        self.preprocess_seconds += time.perf_counter()-start
        image = None
        try:
            with self.torch.inference_mode(), self.torch.cuda.stream(self.stream):
                image = self.torch.from_numpy(chw)[None].to(f'cuda:{self.device}')
                if not self.context.set_tensor_address('image', image.data_ptr()) or not self.context.set_tensor_address('depth', self.output.data_ptr()):
                    raise RuntimeError('DA2 Base buffer binding failed')
                if not self.context.execute_async_v3(self.stream.cuda_stream):
                    raise RuntimeError('DA2 Base execution failed')
                result = self.torch.nn.functional.interpolate(self.output[:,None], frame.shape[:2],
                    mode='bilinear', align_corners=True)[:,0].cpu().numpy().copy()
            self.stream.synchronize()
            if not np.isfinite(result).all():
                raise ValueError('DA2 Base produced nonfinite depth')
            self.calls += 1
            return result
        except BaseException as primary:
            try:
                self.close()  # Synchronize while bound input remains owned locally.
            except Exception as cleanup:
                primary.add_note(str(cleanup))
            raise

    def telemetry(self):
        self._check()
        return dict(model_id='da2-base', runtime='tensorrt-fp32', input_shape=[1,3,*self.shape],
            completed_inferences=self.calls, plan_sha256=PROFILES[self.shape][0], weight_license='CC-BY-NC-4.0',
            preprocessing_ms=self.preprocess_seconds*1000, zero_copy=False,
            host_to_device_bytes=self.calls*3*self.shape[0]*self.shape[1]*4,
            cuda_allocated_bytes=self.torch.cuda.memory_allocated(self.device),
            cuda_peak_allocated_bytes=self.torch.cuda.max_memory_allocated(self.device),
            memory_scope='PyTorch allocator only; TensorRT allocations excluded')

    def close(self):
        if threading.get_ident() != self.owner:
            raise RuntimeError('DA2 Base must close on owner thread')
        if self.closed:
            return
        try:
            if self.stream is not None:
                self.stream.synchronize()
        finally:
            self.output = self.context = self.engine = self.runtime = self.stream = None
            if self.dll is not None:
                self.dll.close()
                self.dll = None
            self.closed = True

    def __enter__(self):
        self._check()
        return self

    def __exit__(self, *exc):
        self.close()
