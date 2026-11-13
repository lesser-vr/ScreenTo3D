"""Owned source-sized DA2 Base depth for the shared live CUDA consumer."""

from dataclasses import dataclass
import os
import time

from .da2_base import Da2BaseEngine, depth_content, preprocess


@dataclass(frozen=True)
class Da2BaseDeviceDepth:
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
            raise RuntimeError("DA2 Base device depth is not the pending owned result")
        if self.owner.device_generation != self.generation:
            raise RuntimeError("DA2 Base device depth expired")
        if (self.tensor.device.type != "cuda"
                or self.tensor.device.index != self.owner.device
                or self.tensor.dtype != self.owner.torch.float32
                or not self.tensor.is_contiguous()
                or self.shape != (1, *self.owner.source_shape)):
            raise ValueError("Invalid DA2 Base device tensor")
        if self.stream != int(self.owner.stream.cuda_stream) or not self.pointer:
            raise RuntimeError("Invalid DA2 Base device binding")


from .environment import get as app_env

class Da2BaseDeviceEngine(Da2BaseEngine):
    """Keep the existing FP32 preprocessing/unpadding/interpolation contract.

    One token owns all input/output allocations until its same-stream consumer
    completes. Host inference remains available for an explicit reference run.
    """

    def __init__(self, *args, **kwargs):
        self.graph = self.graph_input = None
        # Explicit diagnostic candidate. Matched live measurements did not
        # establish enough benefit to promote it to the default path.
        graph_setting = app_env('SCREENTO3D_BASE_GRAPH', '0')
        if graph_setting not in ('0', '1'):
            raise ValueError('SCREENTO3D_BASE_GRAPH must be 0 or 1')
        self.graph_enabled = graph_setting == '1'
        self.pending_device = None
        self.device_generation = 0
        self.device_submissions = self.device_completions = 0
        self.depth_bytes_avoided = 0
        self.source_shape = None
        super().__init__(*args, **kwargs)
        self.profile = self.shape
        self.input_path = app_env('SCREENTO3D_BASE_INPUT', 'gpu')
        self.input_upload_bytes = 0
        self.last_input_bytes = 0
        self.gpu_input = None
        self.stage_events = None
        self.last_stage_ms = {}
        if app_env('SCREENTO3D_BASE_STAGE_PROFILE', '0') == '1':
            self.stage_events = [self.torch.cuda.Event(enable_timing=True) for _ in range(5)]
        try:
            if self.input_path not in ('cpu', 'gpu'):
                raise ValueError('SCREENTO3D_BASE_INPUT must be cpu or gpu')
            if self.input_path == 'gpu':
                from .base_gpu_input import BaseGpuInput
                self.gpu_input = BaseGpuInput(self)
            if self.graph_enabled and self.gpu_input is None:
                raise ValueError('Base CUDA graph requires GPU preprocessing')
            if self.graph_enabled:
                with self.torch.cuda.stream(self.stream):
                    self.graph_input = self.torch.empty(
                        (1, 3, *self.shape), device=f'cuda:{self.device}', dtype=self.torch.float32)
        except BaseException:
            self.close()
            raise

    def infer(self, frame):
        self._check()
        if self.pending_device is not None:
            raise RuntimeError("Complete DA2 Base device depth before host inference")
        result = super().infer(frame)
        self.input_upload_bytes += 3 * self.shape[0] * self.shape[1] * 4
        return result

    def infer_device(self, frame):
        self._check()
        if self.pending_device is not None:
            raise RuntimeError("Complete DA2 Base device depth before another inference")
        import numpy as np
        from .da2_base import content_rect
        from .gpu_frame import GpuFrame
        gpu_frame = isinstance(frame, GpuFrame)
        if gpu_frame:
            frame.validate(self)
            if self.gpu_input is None:
                raise ValueError('GPU capture requires GPU preprocessing')
        if not isinstance(frame, (np.ndarray, GpuFrame)) or frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError('DA2 Base requires uint8 RGB')
        content_rect(frame.shape[1], frame.shape[0], self.shape)
        began = time.perf_counter()
        chw = preprocess(frame, self.shape) if self.gpu_input is None else None
        image = resized = rgb = None
        try:
            with self.torch.inference_mode(), self.torch.cuda.stream(self.stream):
                if self.stage_events:
                    self.stage_events[0].record(self.stream)
                if self.gpu_input is None:
                    image = self.torch.from_numpy(chw)[None].to(f"cuda:{self.device}")
                    self.last_input_bytes = chw.nbytes
                else:
                    rgb = frame.rgb if gpu_frame else self.torch.from_numpy(np.ascontiguousarray(frame)).to(f'cuda:{self.device}')
                    image = self.gpu_input.prepare(rgb, self.graph_input)
                    self.last_input_bytes = 0 if gpu_frame else frame.nbytes
                self.input_upload_bytes += self.last_input_bytes
                self.preprocess_seconds += time.perf_counter() - began
                if self.stage_events:
                    self.stage_events[1].record(self.stream)
                if (not self.context.set_tensor_address("image", image.data_ptr())
                        or not self.context.set_tensor_address("depth", self.output.data_ptr())):
                    raise RuntimeError("DA2 Base buffer binding failed")
                if self.graph_enabled:
                    if self.graph is None:
                        # Warm TensorRT's lazy state before capturing only its
                        # fixed-address inference. Input/depth consumers remain
                        # on the same stream with the existing token lifetime.
                        if not self.context.execute_async_v3(self.stream.cuda_stream):
                            raise RuntimeError('Base graph warmup failed')
                        self.stream.synchronize()
                        self.graph = self.torch.cuda.CUDAGraph()
                        with self.torch.cuda.graph(self.graph, stream=self.stream):
                            if not self.context.execute_async_v3(self.stream.cuda_stream):
                                raise RuntimeError('Base graph capture failed')
                    self.graph.replay()
                elif not self.context.execute_async_v3(self.stream.cuda_stream):
                    raise RuntimeError("DA2 Base execution failed")
                if self.stage_events:
                    self.stage_events[2].record(self.stream)
                content = depth_content(self.output[:, None], frame.shape[1], frame.shape[0])
                resized = self.torch.nn.functional.interpolate(
                    content, frame.shape[:2], mode="bilinear", align_corners=True
                )[:, 0].contiguous()
                if self.stage_events:
                    self.stage_events[3].record(self.stream)
                # Preserve the host engine's finite-output guarantee; only a
                # scalar result crosses to CPU, never the full depth image.
                if not bool(self.torch.isfinite(resized).all()):
                    raise ValueError("DA2 Base produced nonfinite depth")
                if self.stage_events:
                    self.stage_events[4].record(self.stream)
            self.calls += 1
            self.source_shape = frame.shape[:2]
            self.device_generation += 1
            token = Da2BaseDeviceDepth(
                self, self.device_generation, resized,
                int(self.stream.cuda_stream), (image, self.output, rgb),
            )
            self.pending_device = token
            self.device_submissions += 1
            token.validate()
            return token
        except BaseException as primary:
            try:
                self.close()
            except Exception as cleanup:
                primary.add_note(f"DA2 Base device cleanup: {cleanup}")
            raise

    def complete_device(self, token):
        if token.owner is not self:
            raise ValueError("Depth belongs to another engine")
        token.validate()
        self.stream.synchronize()
        if self.stage_events:
            self.last_stage_ms = dict(zip(('input', 'model', 'upscale', 'finite_wait'),
                (a.elapsed_time(b) for a, b in zip(self.stage_events, self.stage_events[1:]))))
        self.depth_bytes_avoided += token.tensor.numel() * token.tensor.element_size()
        self.pending_device = None
        self.device_completions += 1

    def telemetry(self):
        result = super().telemetry()
        result.update(
            device_depth_output=True,
            device_depth_submissions=self.device_submissions,
            device_depth_completions=self.device_completions,
            pending_device_depth=self.pending_device is not None,
            depth_d2h_bytes_avoided=self.depth_bytes_avoided,
            input_preprocessing=self.input_path,
            cuda_graph=self.graph_enabled,
            host_to_device_bytes=self.input_upload_bytes,
            preprocessing_timing_scope='CPU preparation and submission; GPU execution included in inference wait',
        )
        return result

    def close(self):
        # Parent close enforces the owner thread and waits before releasing the
        # stream. Retain the token's allocations until that wait has completed.
        import threading
        if threading.get_ident() != self.owner:
            raise RuntimeError('DA2 Base must close on owner thread')
        error = None
        if self.graph is not None:
            try:
                self.stream.synchronize()
            except Exception as exc:
                error = exc
            try:
                self.graph.reset()
            except Exception as exc:
                if error is None:
                    error = exc
                else:
                    error.add_note(f'CUDA graph release: {exc}')
            self.graph = None
        try:
            super().close()
        except Exception as exc:
            if error is None:
                error = exc
            else:
                error.add_note(f'Base engine cleanup: {exc}')
        finally:
            if self.closed:
                self.pending_device = None
                self.gpu_input = None
                self.graph_input = None
                self.stage_events = None
                self.device_generation += 1
        if error is not None:
            raise error
