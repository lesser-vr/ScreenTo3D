"""VDA Small TensorRT streaming backend with FP32 image, depth and cache bindings."""
import gc
import threading
import time
from pathlib import Path

import numpy as np
import torch

from .vda_artifacts import load_manifest, cache_layout, content_rect
from .vda_preprocess import preprocess
from .engine_cache import device_identity
from .resources import prepare_dll_search_path

class VdaEngine:
    def __init__(self, directory, runtime_dir, progress=None):
        self.owner = threading.get_ident()
        self.closed = False
        self.engines = {}
        self.history = []
        self.stream = self.runtime = self.dll = None
        self.shape = None
        self.calls = self.resets = self.peak = self.upload_bytes = self.download_bytes = 0
        self.preprocess_seconds = 0.0
        self.directory = Path(directory).resolve(strict=True)
        self.manifest = load_manifest(self.directory)
        self.input_shape = tuple(self.manifest['input_shape'])
        if not torch.cuda.is_available():
            raise RuntimeError('VDA requires CUDA; CPU fallback is disabled')
        self.device = torch.cuda.current_device()
        if (self.manifest.get('validation') == 'local-depth-and-cache-samples'
                and device_identity(self.device) != device_identity()):
            raise RuntimeError('VDA engine was built for a different GPU')
        if (list(torch.cuda.get_device_capability()) != self.manifest['compute_capability'] or
                torch.cuda.get_device_name() != self.manifest['gpu']):
            raise RuntimeError('VDA engine GPU does not match this device')
        try:
            self.dll = prepare_dll_search_path(runtime_dir)
            import tensorrt as trt
            self.trt = trt
            if trt.__version__ != self.manifest['tensorrt']:
                raise RuntimeError('VDA TensorRT version mismatch; rebuild the engines')
            self.logger = trt.Logger(trt.Logger.WARNING)
            self.runtime = trt.Runtime(self.logger)
            self.stream = torch.cuda.Stream(device=self.device)
            for name in ('warmup', 'cached'):
                record = self.manifest['engines'][name]
                path = self.directory / record['file']
                payload = path.read_bytes()
                import hashlib
                if hashlib.sha256(payload).hexdigest() != record['sha256']:
                    raise RuntimeError('VDA engine changed after validation')
                engine = self.runtime.deserialize_cuda_engine(payload)
                if engine is None:
                    raise RuntimeError('VDA engine deserialization failed')
                # Register ownership before validation/context creation can fail.
                self.engines[name] = (engine, None)
                self._validate_engine(engine, name)
                context = engine.create_execution_context()
                if context is None:
                    raise RuntimeError('VDA execution context creation failed')
                self.engines[name] = (engine, context)
                engine = context = None
        except BaseException as primary:
            engine = context = None
            try:
                self.close()
            except Exception as cleanup:
                primary.add_note(f'VDA cleanup: {cleanup}')
            raise

    def _validate_engine(self, engine, name):
        expected = {'image': (self.input_shape, True), 'depth': ((1, 1, *self.input_shape[-2:]), False)}
        for i, (spatial, channels) in enumerate(cache_layout(self.input_shape[-2:])):
            expected[f'new_cache_{i}'] = ((spatial, 1, channels), False)
            if name == 'cached':
                expected[f'cache_{i}'] = ((spatial, 31, channels), True)
        names = {engine.get_tensor_name(i) for i in range(engine.num_io_tensors)}
        if names != set(expected):
            raise ValueError('VDA engine tensor names/count do not match the contract')
        for key, (shape, is_input) in expected.items():
            if (tuple(engine.get_tensor_shape(key)) != shape or engine.get_tensor_dtype(key) != self.trt.float32 or
                    (engine.get_tensor_mode(key) == self.trt.TensorIOMode.INPUT) != is_input):
                raise ValueError(f'Invalid VDA tensor contract: {key}')

    def _check(self):
        if threading.get_ident() != self.owner:
            raise RuntimeError('VDA must run on its owner thread')
        if self.closed:
            raise RuntimeError('VDA backend is closed')
        if torch.cuda.current_device() != self.device:
            raise RuntimeError('VDA CUDA device changed')

    def reset(self, reason):
        self._check()
        if reason not in ('start', 'scene_cut', 'source_change', 'discontinuity'):
            raise ValueError('Unknown VDA reset reason')
        self.stream.synchronize()
        self.history.clear()
        self.shape = None
        self.resets += 1

    def _execute(self, image):
        warmup = not self.history
        engine, context = self.engines['warmup' if warmup else 'cached']
        inputs = {'image': image}
        if not warmup:
            selected = self.history[:2] + self.history[-29:]
            if len(selected) != 31:
                raise RuntimeError('Invalid VDA cache history')
            inputs.update({f'cache_{i}': torch.cat([entry[i] for entry in selected], dim=1).contiguous() for i in range(8)})
        outputs = {}
        for i in range(engine.num_io_tensors):
            name = engine.get_tensor_name(i)
            if name in inputs:
                tensor = inputs[name]
            else:
                tensor = torch.empty(tuple(engine.get_tensor_shape(name)), device=image.device, dtype=torch.float32)
                outputs[name] = tensor
            if not context.set_tensor_address(name, tensor.data_ptr()):
                raise RuntimeError('VDA tensor binding failed')
        # All bound buffers must remain alive through submission AND completion.
        try:
            if not context.execute_async_v3(self.stream.cuda_stream):
                raise RuntimeError('VDA inference submission failed')
        finally:
            self.stream.synchronize()
        if not all(torch.isfinite(value).all().item() for value in outputs.values()):
            raise RuntimeError('VDA produced nonfinite depth/cache values')
        cache = tuple(outputs[f'new_cache_{i}'] for i in range(8))
        self.history = [cache] * 32 if warmup else self.history + [cache]
        if len(self.history) > 42:
            del self.history[1]
        self.peak = max(self.peak, len(self.history))
        return outputs['depth']

    def _source_depth(self, depth, frame):
        height, width = frame.shape[:2]
        y, x, h, w = content_rect(width, height, self.input_shape[-2:])
        return torch.nn.functional.interpolate(depth[..., y:y+h, x:x+w],
            size=(height, width), mode='bilinear', align_corners=True)[0]

    def infer(self, frame):
        self._check()
        started = time.perf_counter()
        chw = preprocess(frame, self.input_shape[-2:])
        self.preprocess_seconds += time.perf_counter() - started
        if self.shape is not None and self.shape != frame.shape:
            raise ValueError('Reset VDA before changing source dimensions')
        try:
            with torch.no_grad(), torch.cuda.stream(self.stream):
                image = torch.from_numpy(chw)[None, None].to(f'cuda:{self.device}')
                self.upload_bytes += chw.nbytes
                depth = self._execute(image)
                result = self._source_depth(depth, frame).cpu().numpy().copy()
            if not np.isfinite(result).all():
                raise RuntimeError('VDA returned invalid resized depth')
            self.calls += 1
            self.download_bytes += result.nbytes
            self.shape = frame.shape
            return result
        except BaseException as primary:
            try:
                self.close()
            except Exception as cleanup:
                primary.add_note(f'VDA cleanup: {cleanup}')
            raise

    def telemetry(self):
        self._check()
        return dict(completed_inferences=self.calls, resets=self.resets, cache_entries=len(self.history),
            peak_cache_entries=self.peak, cache_entry_limit=42, zero_copy=False,
            runtime=f"TensorRT {self.manifest.get('precision', 'fp32').upper()}; torch CUDA buffers", input_shape=list(self.input_shape),
            host_to_device_bytes=self.upload_bytes, device_to_host_bytes=self.download_bytes,
            preprocessing_ms=self.preprocess_seconds * 1000,
            preprocessing_timing_scope='Included in pipeline depth timing; do not add twice',
            cuda_allocated_bytes=torch.cuda.memory_allocated(self.device),
            cuda_reserved_bytes=torch.cuda.memory_reserved(self.device),
            allocator_scope='process-global; not a leak proof',
            plan_hashes={name: item['sha256'] for name, item in self.manifest['engines'].items()})

    def close(self):
        if threading.get_ident() != self.owner:
            raise RuntimeError('VDA must be closed by its owner thread')
        if self.closed:
            return
        self.closed = True
        try:
            if self.stream is not None:
                self.stream.synchronize()
        finally:
            self.history.clear()
            for name in tuple(self.engines):
                engine, context = self.engines.pop(name)
                del context
                del engine
            self.runtime = self.stream = None
            gc.collect()
            if self.dll is not None:
                self.dll.close()
                self.dll = None

    def __enter__(self):
        self._check()
        return self

    def __exit__(self, kind, value, traceback):
        try:
            self.close()
        except Exception as cleanup:
            if value is None:
                raise
            value.add_note(f'VDA cleanup: {cleanup}')
        return False
