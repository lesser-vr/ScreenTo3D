"""Local DA2 Base mixed-FP16 engine with FP32 I/O; CC-BY-NC-4.0 weights."""
import hashlib
import os
from pathlib import Path
import threading
import time

import cv2
import numpy as np

PRECISION = 'fp16'
PLAN_HASH = 'a8718fa657e73f7506ab71367e4ec2d4600338bb72a8d2c142c94e7ef0a86eb7'
PLAN_BYTES = 200603884
SHAPE = (1, 3, 518, 896)
PROFILES = {
    (518, 896): (PLAN_HASH, PLAN_BYTES),
    (518, 924): ('0216c0493714c120ebe261d29eb10b3eadb52ca8fc5934192aa2dbf2570bd9bd', 200667716),
}


def content_rect(width, height, shape):
    """Top, left, height, width of source content in a trusted model canvas."""
    if (type(width) is not int or type(height) is not int or
            not (16 <= width <= 4096 and 16 <= height <= 2160)):
        raise ValueError('DA2 Base source must be 16..4096 pixels wide and 16..2160 high')
    if shape not in PROFILES:
        raise ValueError('Unvalidated DA2 Base engine shape')
    h, w = shape
    # Keep the original upstream patch-rounded resize exactly for legacy inputs.
    scale = 518 / min(width, height)
    if (max(width, height)/min(width, height) <= 1.78 and
            tuple(max(518, round(n*scale/14)*14) for n in (height, width)) == shape):
        return 0, 0, h, w
    scale = min(w / width, h / height)
    rh, rw = max(1, round(height*scale)), max(1, round(width*scale))
    return (h-rh)//2, (w-rw)//2, rh, rw


def preprocess(frame, shape=(518,896)):
    if not isinstance(frame, np.ndarray) or frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError('DA2 Base requires uint8 RGB')
    top, left, rh, rw = content_rect(frame.shape[1], frame.shape[0], shape)
    # DA2 upstream divides uint8 by 255 before resize (float64, unlike VDA).
    image = cv2.resize(frame / 255.0, (rw, rh), interpolation=cv2.INTER_CUBIC)
    if (rh, rw) != shape:
        image = cv2.copyMakeBorder(image, top, shape[0]-rh-top, left, shape[1]-rw-left,
                                   cv2.BORDER_REPLICATE)
    return np.ascontiguousarray(((image-[.485,.456,.406])/[.229,.224,.225]).transpose(2,0,1), dtype=np.float32)


def depth_content(depth, width, height):
    """Slice off model-only padding before interpolating to source pixels."""
    y, x, h, w = content_rect(width, height, tuple(depth.shape[-2:]))
    return depth[..., y:y+h, x:x+w]


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
        child = directory/f'{shape[0]}x{shape[1]}-{PRECISION}'
        if child.exists():
            child = child.resolve(strict=True)
            if child.parent != directory:
                raise ValueError('DA2 Base profile escapes selected directory')
            checked_plan(child, shape)
            found[shape] = child
    if not found:
        raise ValueError(f'No validated DA2 Base {PRECISION.upper()} profiles found; install the matching local engines')
    return found


def binding(directory, runtime_dir, *, device_depth=False):
    from .depth_backend import BackendBinding, BackendSpec
    if directory is None or runtime_dir is None:
        raise ValueError('DA2 Base requires engine and TensorRT runtime directories')
    installed = profiles(directory)
    if not (Path(runtime_dir)/'nvinfer_11.dll').is_file():
        raise ValueError('TensorRT 11 runtime not found')
    selected = next(iter(installed)) if len(installed) == 1 else None
    def validate(metadata):
        nonlocal selected
        selected = None
        def occupancy(shape):
            _, _, h, w = content_rect(metadata['width'], metadata['height'], shape)
            return (h*w)/(shape[0]*shape[1])
        selected = max(installed, key=occupancy)
    def factory(progress):
        if selected is None:
            raise ValueError('Select DA2 Base profile with input preflight first')
        if progress:
            progress(dict(event='da2_base_profile', input_shape=[1,3,*selected]))
        engine_type = Da2BaseEngine
        if device_depth:
            from .da2_base_device import Da2BaseDeviceEngine
            engine_type = Da2BaseDeviceEngine
        return engine_type(installed[selected], runtime_dir, selected)
    return BackendBinding(BackendSpec('da2-base', f'tensorrt-{PRECISION}'), factory, lambda frame: frame, validate)


class Da2BaseEngine:
    def __init__(self, directory, runtime_dir, shape=(518,896)):
        import torch
        self.torch, self.owner = torch, threading.get_ident()
        self.closed = False
        self.stream = self.runtime = self.engine = self.context = self.dll = self.output = None
        self.calls = 0
        self.preprocess_seconds = 0.
        self.shape = shape
        self.precision = PRECISION
        self.plan_hash = PROFILES[shape][0]
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
                content = depth_content(self.output[:, None], frame.shape[1], frame.shape[0])
                result = self.torch.nn.functional.interpolate(content, frame.shape[:2],
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
        return dict(model_id='da2-base', runtime=f'tensorrt-{self.precision}', input_shape=[1,3,*self.shape],
            completed_inferences=self.calls, plan_sha256=self.plan_hash, weight_license='CC-BY-NC-4.0',
            io_precision='fp32',
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
