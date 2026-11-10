"""Owned source-resolution device output for the validated VDA live backend."""

from dataclasses import dataclass
import threading
import time

import torch

from .vda_backend import VdaEngine
from .vda_preprocess import preprocess
from .vda_artifacts import content_rect
from .gpu_frame import GpuFrame
from .gpu_runtime import FixedCanvasGpuInput
from .portable_cuda import DIRECTORY, PINS


@dataclass(frozen=True)
class VdaDeviceDepth:
    owner: object
    generation: int
    tensor: object
    stream: int
    resources: tuple

    @property
    def pointer(self):
        return int(self.tensor.data_ptr())

    @property
    def shape(self):
        return tuple(self.tensor.shape)

    def validate(self):
        self.owner._check()
        if self.owner.pending_device is not self:
            raise RuntimeError("VDA device depth is not the pending owned result")
        if self.owner.device_generation != self.generation:
            raise RuntimeError("VDA device depth expired")
        if self.tensor.device.type != "cuda" or self.tensor.dtype != torch.float32:
            raise ValueError("Invalid VDA device tensor")
        if self.shape != (1, *self.owner.shape[:2]):
            raise ValueError("Invalid VDA device depth shape")
        if self.stream != int(self.owner.stream.cuda_stream) or not self.pointer:
            raise RuntimeError("Invalid VDA device binding")


class VdaDeviceEngine(VdaEngine):
    """Preserve VDA cache semantics while lending resized depth to one consumer."""

    def __init__(self, *args, **kwargs):
        self.pending_device = None
        self.torch = torch
        self._gpu_input = None
        self.last_input_bytes = 0
        self.device_generation = 0
        self.device_submissions = 0
        self.device_completions = 0
        super().__init__(*args, **kwargs)

    @property
    def gpu_input(self):
        self._check()
        if self._gpu_input is None:
            name = 'vda_input.dll'
            self._gpu_input = FixedCanvasGpuInput(self, DIRECTORY/name, PINS[name],
                'vda_prepare', content_rect)
        return self._gpu_input

    def reset(self, reason):
        if self.pending_device is not None:
            raise RuntimeError("Complete VDA device depth before reset")
        super().reset(reason)
        self.device_generation += 1

    def infer_device(self, frame):
        self._check()
        if self.pending_device is not None:
            raise RuntimeError("Complete VDA device depth before another inference")
        started = time.perf_counter()
        if self.shape is not None and self.shape != frame.shape:
            raise ValueError("Reset VDA before changing source dimensions")
        try:
            with torch.no_grad(), torch.cuda.stream(self.stream):
                if isinstance(frame, GpuFrame):
                    frame.validate(self)
                    image = self.gpu_input.prepare(frame.rgb, self.input_shape[-2:]).unsqueeze(1)
                    self.last_input_bytes = 0
                else:
                    chw = preprocess(frame, self.input_shape[-2:])
                    image = torch.from_numpy(chw)[None, None].to(f"cuda:{self.device}")
                    self.last_input_bytes = chw.nbytes
                self.preprocess_seconds += time.perf_counter() - started
                self.upload_bytes += self.last_input_bytes
                depth = self._execute(image)
                resized = self._source_depth(depth, frame).contiguous()
                if not bool(torch.isfinite(resized).all()):
                    raise RuntimeError("VDA returned invalid resized device depth")
            self.calls += 1
            self.shape = frame.shape
            self.device_generation += 1
            token = VdaDeviceDepth(
                self,
                self.device_generation,
                resized,
                int(self.stream.cuda_stream),
                (image, depth),
            )
            self.pending_device = token
            self.device_submissions += 1
            token.validate()
            return token
        except BaseException as primary:
            try:
                self.close()
            except Exception as cleanup:
                primary.add_note(f"VDA device cleanup: {cleanup}")
            raise

    def complete_device(self, token):
        if token.owner is not self:
            raise ValueError("Depth belongs to another VDA engine")
        token.validate()
        self.stream.synchronize()
        self.pending_device = None
        self.device_completions += 1

    def telemetry(self):
        result = super().telemetry()
        result.update(
            device_depth_output=True,
            preprocessing_timing_scope='CPU input preparation/submission; CUDA execution completes during inference',
            device_depth_submissions=self.device_submissions,
            device_depth_completions=self.device_completions,
            pending_device_depth=self.pending_device is not None,
            depth_d2h_bytes_avoided=self.device_completions
            * (self.shape[0] * self.shape[1] * 4 if self.shape else 0),
            zero_copy=False,
        )
        return result

    def close(self):
        if threading.get_ident() != self.owner:
            raise RuntimeError("VDA must be closed by its owner thread")
        if getattr(self, "pending_device", None) is not None:
            if self.stream is not None:
                self.stream.synchronize()
            self.pending_device = None
            self.device_generation += 1
        try:
            super().close()
        finally:
            if self.closed:
                self._gpu_input = None
