"""Owned source-sized DA2 Base depth for the shared live CUDA consumer."""

from dataclasses import dataclass
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


class Da2BaseDeviceEngine(Da2BaseEngine):
    """Keep the existing FP32 preprocessing/unpadding/interpolation contract.

    One token owns all input/output allocations until its same-stream consumer
    completes. Host inference remains available for an explicit reference run.
    """

    def __init__(self, *args, **kwargs):
        self.pending_device = None
        self.device_generation = 0
        self.device_submissions = self.device_completions = 0
        self.depth_bytes_avoided = 0
        self.source_shape = None
        super().__init__(*args, **kwargs)
        self.profile = self.shape

    def infer(self, frame):
        self._check()
        if self.pending_device is not None:
            raise RuntimeError("Complete DA2 Base device depth before host inference")
        return super().infer(frame)

    def infer_device(self, frame):
        self._check()
        if self.pending_device is not None:
            raise RuntimeError("Complete DA2 Base device depth before another inference")
        began = time.perf_counter()
        chw = preprocess(frame, self.shape)
        self.preprocess_seconds += time.perf_counter() - began
        image = resized = None
        try:
            with self.torch.inference_mode(), self.torch.cuda.stream(self.stream):
                image = self.torch.from_numpy(chw)[None].to(f"cuda:{self.device}")
                if (not self.context.set_tensor_address("image", image.data_ptr())
                        or not self.context.set_tensor_address("depth", self.output.data_ptr())):
                    raise RuntimeError("DA2 Base buffer binding failed")
                if not self.context.execute_async_v3(self.stream.cuda_stream):
                    raise RuntimeError("DA2 Base execution failed")
                content = depth_content(self.output[:, None], frame.shape[1], frame.shape[0])
                resized = self.torch.nn.functional.interpolate(
                    content, frame.shape[:2], mode="bilinear", align_corners=True
                )[:, 0].contiguous()
                # Preserve the host engine's finite-output guarantee; only a
                # scalar result crosses to CPU, never the full depth image.
                if not bool(self.torch.isfinite(resized).all()):
                    raise ValueError("DA2 Base produced nonfinite depth")
            self.calls += 1
            self.source_shape = frame.shape[:2]
            self.device_generation += 1
            token = Da2BaseDeviceDepth(
                self, self.device_generation, resized,
                int(self.stream.cuda_stream), (image, self.output),
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
        )
        return result

    def close(self):
        # Parent close enforces the owner thread and waits before releasing the
        # stream. Retain the token's allocations until that wait has completed.
        try:
            super().close()
        finally:
            if self.closed:
                self.pending_device = None
                self.device_generation += 1
