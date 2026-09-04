import hashlib
import json
from pathlib import Path

import numpy as np

from .resources import cache_root, prepare_dll_search_path, resource_path
from .resource_telemetry import ResourceMetrics

prepare_dll_search_path()
import tensorrt as trt  # noqa: E402
from cuda.bindings import runtime as cudart  # noqa: E402


LOGGER = trt.Logger(trt.Logger.WARNING)
INPUT_NAME = "pixel_values"
OUTPUT_NAME = "predicted_depth"
INPUT_SHAPE = (1, 3, 518, 518)
OUTPUT_SHAPE = (1, 518, 518)


def _cuda(result):
    error = result[0]
    if error != cudart.cudaError_t.cudaSuccess:
        raise RuntimeError(f"CUDA failure: {error}")
    if len(result) == 1:
        return None
    if len(result) == 2:
        return result[1]
    return result[1:]


def _model_path() -> Path:
    return resource_path("models/da2-small/model_fp16.onnx")


def _engine_path() -> Path:
    model = _model_path()
    digest = hashlib.sha256(model.read_bytes()).hexdigest()[:16]
    return cache_root() / f"da2-small-{digest}-trt{trt.__version__}-518.plan"


def build_engine(model_path: Path, engine_path: Path) -> None:
    builder = trt.Builder(LOGGER)
    network = builder.create_network(0)
    parser = trt.OnnxParser(network, LOGGER)
    if not parser.parse(model_path.read_bytes()):
        errors = [str(parser.get_error(index)) for index in range(parser.num_errors)]
        raise RuntimeError("ONNX parsing failed: " + " | ".join(errors))
    profile = builder.create_optimization_profile()
    profile.set_shape(INPUT_NAME, INPUT_SHAPE, INPUT_SHAPE, INPUT_SHAPE)
    config = builder.create_builder_config()
    config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, 2 * 1024**3)
    config.add_optimization_profile(profile)
    serialized = builder.build_serialized_network(network, config)
    if serialized is None:
        raise RuntimeError("TensorRT engine build failed")
    temporary = engine_path.with_suffix(engine_path.suffix + ".partial")
    temporary.write_bytes(bytes(serialized))
    temporary.replace(engine_path)


class DepthEngine:
    def __init__(self, progress=None):
        self.metrics = ResourceMetrics()
        model_path = _model_path()
        if not model_path.is_file():
            raise FileNotFoundError(f"Depth model not found: {model_path}")
        engine_path = _engine_path()
        if not engine_path.exists():
            if progress:
                progress({"event": "engine_build", "message": "Optimizing depth engine for this GPU"})
            build_engine(model_path, engine_path)
        runtime = trt.Runtime(LOGGER)
        self.engine = runtime.deserialize_cuda_engine(engine_path.read_bytes())
        if self.engine is None:
            engine_path.unlink(missing_ok=True)
            build_engine(model_path, engine_path)
            self.engine = runtime.deserialize_cuda_engine(engine_path.read_bytes())
        if self.engine is None:
            raise RuntimeError("TensorRT engine deserialization failed")
        self.context = self.engine.create_execution_context()
        if not self.context.set_input_shape(INPUT_NAME, INPUT_SHAPE):
            raise RuntimeError("TensorRT input shape rejected")
        self.input_bytes = int(np.prod(INPUT_SHAPE) * np.dtype(np.float32).itemsize)
        self.output_bytes = int(np.prod(OUTPUT_SHAPE) * np.dtype(np.float32).itemsize)
        self.device_input = _cuda(cudart.cudaMalloc(self.input_bytes))
        self.device_output = _cuda(cudart.cudaMalloc(self.output_bytes))
        self.stream = _cuda(cudart.cudaStreamCreate())
        self.output = np.empty(OUTPUT_SHAPE, dtype=np.float32)
        self.context.set_tensor_address(INPUT_NAME, int(self.device_input))
        self.context.set_tensor_address(OUTPUT_NAME, int(self.device_output))
        self._sample_memory(force=True)

    def _sample_memory(self, force=False):
        self.metrics.sample_memory(lambda: _cuda(cudart.cudaMemGetInfo()), force=force)

    def telemetry(self):
        self._sample_memory(force=True)
        result = self.metrics.summary()
        result['explicit_io_buffer_bytes'] = self.input_bytes + self.output_bytes
        return result

    def infer(self, tensor: np.ndarray) -> np.ndarray:
        contiguous = np.ascontiguousarray(tensor, dtype=np.float32)
        if contiguous.shape != INPUT_SHAPE:
            raise ValueError(f"invalid depth input shape: {contiguous.shape}")
        _cuda(cudart.cudaMemcpyAsync(
            self.device_input,
            contiguous.ctypes.data,
            self.input_bytes,
            cudart.cudaMemcpyKind.cudaMemcpyHostToDevice,
            self.stream,
        ))
        self.metrics.copy_submitted('h2d', self.input_bytes)
        if not self.context.execute_async_v3(stream_handle=int(self.stream)):
            raise RuntimeError("TensorRT inference submission failed")
        _cuda(cudart.cudaMemcpyAsync(
            self.output.ctypes.data,
            self.device_output,
            self.output_bytes,
            cudart.cudaMemcpyKind.cudaMemcpyDeviceToHost,
            self.stream,
        ))
        self.metrics.copy_submitted('d2h', self.output_bytes)
        _cuda(cudart.cudaStreamSynchronize(self.stream))
        self.metrics.counters['stream_synchronizations'] += 1
        if not np.isfinite(self.output).all():
            raise RuntimeError("depth output contains non-finite values")
        self.metrics.counters['completed_inferences'] += 1
        self._sample_memory()
        return self.output.copy()

    def close(self) -> None:
        if getattr(self, "device_input", None) is not None:
            _cuda(cudart.cudaFree(self.device_input))
            self.device_input = None
        if getattr(self, "device_output", None) is not None:
            _cuda(cudart.cudaFree(self.device_output))
            self.device_output = None
        if getattr(self, "stream", None) is not None:
            _cuda(cudart.cudaStreamDestroy(self.stream))
            self.stream = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def diagnostics() -> dict:
    count = _cuda(cudart.cudaGetDeviceCount())
    return {
        "tensorrt": trt.__version__,
        "cuda_devices": int(count),
        "model": str(_model_path()),
        "engine_cache": str(_engine_path()),
    }
