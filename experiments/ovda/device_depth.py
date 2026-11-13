# Derived oVDA experiment; NC-SA-UHDV1.0. See LICENSE and README.md.
"""Owned device-depth output for the optional source-only oVDA backend."""

from dataclasses import dataclass
import threading

import torch

from .oracle import schedule
from .preprocessing import validate_frame
from .trt_engine import OvdaTrt


@dataclass(frozen=True)
class OvdaDeviceDepth:
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
        self.owner.check()
        if self.owner.pending_device is not self:
            raise RuntimeError("oVDA device depth is not the pending owned result")
        if self.owner.device_generation != self.generation:
            raise RuntimeError("oVDA device depth expired")
        if self.tensor.device.type != "cuda" or self.tensor.dtype != torch.float32:
            raise ValueError("Invalid oVDA device tensor")
        if self.shape != (1, *self.owner.shape[:2]):
            raise ValueError("Invalid oVDA device depth shape")
        if self.stream != int(self.owner.stream.cuda_stream) or not self.pointer:
            raise RuntimeError("Invalid oVDA device binding")


class OvdaDeviceTrt(OvdaTrt):
    """Same model/cache semantics, returning depth on CUDA until completion."""

    def __init__(self, *args, **kwargs):
        self.pending_device = None
        self.torch = torch
        self._gpu_input = None
        self._buffers = None
        self.last_input_bytes = 0
        self.input_upload_bytes = 0
        self.gpu_input_calls = 0
        self.device_generation = 0
        self.device_submissions = 0
        self.device_completions = 0
        super().__init__(*args, **kwargs)

    def _check(self):
        self.check()

    @property
    def gpu_input(self):
        self.check()
        if self._gpu_input is None:
            from .gpu_input import OvdaGpuInput
            self._gpu_input = OvdaGpuInput(self)
        return self._gpu_input

    def reset(self, reason):
        self.check()
        if self.pending_device is not None:
            raise RuntimeError("Complete oVDA device depth before reset")
        if reason not in ('start','scene_cut','source_change','discontinuity'):
            raise ValueError('Unknown reset reason')
        with torch.inference_mode(),torch.cuda.stream(self.stream):
            for value in self.cache.values():value.zero_()
        self.stream.synchronize()
        self.used=0
        self.shape=None
        self.resets+=1
        self.device_generation += 1

    def infer_device(self, frame):
        self.check()
        if self.pending_device is not None:
            raise RuntimeError("Complete oVDA device depth before another inference")
        from screento3d_app.gpu_frame import GpuFrame
        if isinstance(frame, GpuFrame):
            frame.validate(self)
        else:
            validate_frame(frame)
        if self.shape is not None and self.shape != frame.shape:
            raise ValueError("Reset before geometry change")
        try:
            with torch.inference_mode(), torch.cuda.stream(self.stream):
                if self._buffers is None:
                    from .device_buffers import OvdaBuffers
                    self._buffers=OvdaBuffers(self)
                buffers=self._buffers
                image=buffers.image
                if isinstance(frame, GpuFrame):
                    self.gpu_input.prepare(frame.rgb, self.profile, output=image[:,0])
                    self.last_input_bytes = 0
                    self.gpu_input_calls += 1
                else:
                    image.copy_(self.pre.preprocess(frame.copy()))
                    self.last_input_bytes = image.numel()*image.element_size()
                self.input_upload_bytes += self.last_input_bytes
                if not self.cache:
                    self.cache = {
                        key: torch.zeros(
                            (1, 2, n, 16, channels),
                            device=image.device,
                            dtype=torch.float32,
                        )
                        for key, (n, channels) in self.caches.items()
                    }
                mask, position = buffers.schedules[self.used]
                inputs = {
                    "image": image,
                    "mask": mask,
                    "position": position,
                    **{f"cache_{key}": value for key, value in self.cache.items()},
                }
                outputs = buffers.outputs
                for name, (shape, dtype, is_input) in self.signature.items():
                    tensor = (
                        inputs[name]
                        if is_input
                        else outputs[name]
                    )
                    if not is_input:
                        outputs[name] = tensor
                    expected = (
                        torch.float32 if dtype == self.trt.float32 else torch.int64
                    )
                    if (
                        tuple(tensor.shape) != shape
                        or tensor.dtype != expected
                        or not tensor.is_contiguous()
                        or tensor.device != image.device
                    ):
                        raise ValueError(
                            "Bound buffer shape/dtype/layout/device mismatch"
                        )
                    if not self.context.set_tensor_address(name, tensor.data_ptr()):
                        raise RuntimeError("Binding failed")
                if not self.context.execute_async_v3(self.stream.cuda_stream):
                    raise RuntimeError("Execution failed")
                buffers.check_outputs()
                if self.used == 15:
                    buffers.shift_caches()
                else:
                    for key in self.cache:
                        self.cache[key][:, :, :, self.used, :] = outputs[f"new_{key}"][
                            :, :, :, 0, :
                        ]
                self.used = min(self.used + 1, 15)
                result = self.pre.restore_depth(outputs["depth"], frame.shape[:2])[:, 0].contiguous()
            self.calls += 1
            self.shape = frame.shape
            self.device_generation += 1
            token = OvdaDeviceDepth(
                self,
                self.device_generation,
                result,
                int(self.stream.cuda_stream),
                (image, *outputs.values()),
            )
            self.pending_device = token
            self.device_submissions += 1
            token.validate()
            return token
        except BaseException as primary:
            try:
                self.close()
            except Exception as error:
                primary.add_note(str(error))
            raise

    def complete_device(self, token):
        if token.owner is not self:
            raise ValueError('Depth belongs to another oVDA engine')
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
            gpu_input_calls=self.gpu_input_calls,
            input_upload_bytes=self.input_upload_bytes,
            fixed_inference_buffer_bytes=self._buffers.bytes() if self._buffers else 0,
            output_validation_waits=self._buffers.checks if self._buffers else 0,
            cache_bank_count=1 if self.cache else 0,
            depth_d2h_bytes_avoided=self.device_completions
            * (self.shape[0] * self.shape[1] * 4 if self.shape else 0),
            zero_copy=False,
        )
        return result

    def close(self):
        if threading.get_ident()!=self.owner:
            raise RuntimeError('oVDA close requires owner thread')
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
                self._buffers = None


class OvdaBufferedDeviceTrt(OvdaDeviceTrt):
    """Allocation spike with fixed outputs, schedules and two cache banks."""

    def __init__(self, *args, **kwargs):
        self.cache_banks = None
        self.active_cache_bank = 0
        self.output_buffers = None
        self.schedule_buffers = None
        super().__init__(*args, **kwargs)

    def reset(self, reason):
        self.check()
        if self.pending_device is not None:
            raise RuntimeError("Complete oVDA device depth before reset")
        if reason not in ("start", "scene_cut", "source_change", "discontinuity"):
            raise ValueError("Unknown reset reason")
        self.stream.synchronize()
        self.used = 0
        self.shape = None
        self.resets += 1
        self.device_generation += 1
        self.active_cache_bank = 0
        if self.cache_banks is None:
            self.cache.clear()
        else:
            with torch.inference_mode(), torch.cuda.stream(self.stream):
                for bank in self.cache_banks:
                    for value in bank.values():
                        value.zero_()
            self.stream.synchronize()
            self.cache = self.cache_banks[0]

    def _allocate_buffers(self, device):
        if self.cache_banks is not None:
            return
        self.cache_banks = tuple(
            {
                key: torch.zeros(
                    (1, 2, n, 16, channels),
                    device=device,
                    dtype=torch.float32,
                )
                for key, (n, channels) in self.caches.items()
            }
            for _ in range(2)
        )
        self.cache = self.cache_banks[0]
        self.output_buffers = {
            name: torch.empty(shape, device=device, dtype=torch.float32)
            for name, (shape, _, is_input) in self.signature.items()
            if not is_input
        }
        self.schedule_buffers = tuple(
            (
                torch.tensor(schedule(used)[0], device=device, dtype=torch.int64),
                torch.tensor(schedule(used)[1], device=device, dtype=torch.int64),
            )
            for used in range(16)
        )

    def infer_device(self, frame):
        self.check()
        if self.pending_device is not None:
            raise RuntimeError("Complete oVDA device depth before another inference")
        validate_frame(frame)
        if self.shape is not None and self.shape != frame.shape:
            raise ValueError("Reset before geometry change")
        try:
            with torch.inference_mode(), torch.cuda.stream(self.stream):
                image = (
                    self.pre.preprocess(frame.copy())
                    .to(f"cuda:{self.device}")
                    .contiguous()
                )
                self._allocate_buffers(image.device)
                mask, position = self.schedule_buffers[self.used]
                inputs = {
                    "image": image,
                    "mask": mask,
                    "position": position,
                    **{f"cache_{key}": value for key, value in self.cache.items()},
                }
                outputs = self.output_buffers
                for name, (shape, dtype, is_input) in self.signature.items():
                    tensor = inputs[name] if is_input else outputs[name]
                    expected = (
                        torch.float32 if dtype == self.trt.float32 else torch.int64
                    )
                    if (
                        tuple(tensor.shape) != shape
                        or tensor.dtype != expected
                        or not tensor.is_contiguous()
                        or tensor.device != image.device
                    ):
                        raise ValueError(
                            "Bound buffer shape/dtype/layout/device mismatch"
                        )
                    if not self.context.set_tensor_address(name, tensor.data_ptr()):
                        raise RuntimeError("Binding failed")
                if not self.context.execute_async_v3(self.stream.cuda_stream):
                    raise RuntimeError("Execution failed")
                self.stream.synchronize()
                if not all(
                    bool(torch.isfinite(value).all()) for value in outputs.values()
                ):
                    raise ValueError("Nonfinite oVDA output")
                if self.used == 15:
                    destination_index = 1 - self.active_cache_bank
                    destination = self.cache_banks[destination_index]
                    for key, value in self.cache.items():
                        destination[key][:, :, :, :14, :].copy_(value[:, :, :, 1:15, :])
                        destination[key][:, :, :, 14:15, :].copy_(outputs[f"new_{key}"])
                        destination[key][:, :, :, 15:16, :].zero_()
                    self.active_cache_bank = destination_index
                    self.cache = destination
                else:
                    for key in self.cache:
                        self.cache[key][:, :, :, self.used, :] = outputs[f"new_{key}"][
                            :, :, :, 0, :
                        ]
                self.used = min(self.used + 1, 15)
                result = self.pre.restore_depth(outputs["depth"], frame.shape[:2])[:, 0].contiguous()
            self.calls += 1
            self.shape = frame.shape
            self.device_generation += 1
            token = OvdaDeviceDepth(
                self,
                self.device_generation,
                result,
                int(self.stream.cuda_stream),
                (image, outputs),
            )
            self.pending_device = token
            self.device_submissions += 1
            token.validate()
            return token
        except BaseException as primary:
            try:
                self.close()
            except Exception as error:
                primary.add_note(str(error))
            raise

    def telemetry(self):
        result = super().telemetry()
        cache_bytes = sum(
            value.numel() * value.element_size()
            for bank in (self.cache_banks or ())
            for value in bank.values()
        )
        output_bytes = sum(
            value.numel() * value.element_size()
            for value in (self.output_buffers or {}).values()
        )
        result.update(
            fixed_buffer_candidate=True,
            cache_bank_count=2 if self.cache_banks is not None else 0,
            allocated_cache_bytes=cache_bytes,
            allocated_output_bytes=output_bytes,
            fixed_schedule_count=len(self.schedule_buffers or ()),
        )
        return result

    def close(self):
        try:
            super().close()
        finally:
            self.cache_banks = None
            self.output_buffers = None
            self.schedule_buffers = None
