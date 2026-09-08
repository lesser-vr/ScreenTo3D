"""Owned VDA device-depth token experiment; production VdaEngine is unchanged."""

from dataclasses import dataclass
import time

import torch

from depthsbs_app.vda_backend import VdaEngine
from depthsbs_app.vda_preprocess import preprocess


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
    """Same VDA/cache semantics, retaining resized depth through completion."""

    def __init__(self, *args, **kwargs):
        self.pending_device = None
        self.device_generation = 0
        self.device_submissions = 0
        self.device_completions = 0
        super().__init__(*args, **kwargs)

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
        chw = preprocess(frame, self.input_shape[-2:])
        self.preprocess_seconds += time.perf_counter() - started
        if self.shape is not None and self.shape != frame.shape:
            raise ValueError("Reset VDA before changing source dimensions")
        try:
            with torch.no_grad(), torch.cuda.stream(self.stream):
                image = torch.from_numpy(chw)[None, None].to(f"cuda:{self.device}")
                self.upload_bytes += chw.nbytes
                depth = self._execute(image)
                resized = torch.nn.functional.interpolate(
                    depth.flatten(0, 1).unsqueeze(1),
                    size=frame.shape[:2],
                    mode="bilinear",
                    align_corners=True,
                )[0].contiguous()
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
        token.validate()
        self.stream.synchronize()
        self.pending_device = None
        self.device_completions += 1

    def telemetry(self):
        result = super().telemetry()
        result.update(
            device_depth_output=True,
            device_depth_submissions=self.device_submissions,
            device_depth_completions=self.device_completions,
            pending_device_depth=self.pending_device is not None,
            depth_d2h_bytes_avoided=self.device_completions
            * (self.shape[0] * self.shape[1] * 4 if self.shape else 0),
            zero_copy=False,
        )
        return result

    def close(self):
        if getattr(self, "pending_device", None) is not None:
            if self.stream is not None:
                self.stream.synchronize()
            self.pending_device = None
            self.device_generation += 1
        super().close()
