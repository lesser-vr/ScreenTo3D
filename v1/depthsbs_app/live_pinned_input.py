"""Opt-in page-locked RGB staging candidate for the native live path."""

import ctypes as ct
import threading
import time

import numpy as np

from .live_gpu_candidate import LiveGpuCandidate
from .live_gpu_texture import LiveGpuTexture
from .trt_backend import _cuda, cudart


class PinnedRgbBuffer:
    """One bounded host allocation owned by the CUDA worker thread."""

    def __init__(self, shape):
        if len(shape) != 3 or shape[2] != 3:
            raise ValueError("Invalid pinned RGB shape")
        self.shape = tuple(int(value) for value in shape)
        self.size = int(np.prod(self.shape))
        self.pointer = _cuda(
            cudart.cudaHostAlloc(self.size, cudart.cudaHostAllocDefault)
        )
        try:
            self._owner = (ct.c_ubyte * self.size).from_address(int(self.pointer))
            self.array = np.ctypeslib.as_array(self._owner).reshape(self.shape)
        except BaseException:
            pointer, self.pointer = self.pointer, None
            _cuda(cudart.cudaFreeHost(pointer))
            raise

    def copy(self, frame):
        if frame.dtype != np.uint8 or frame.shape != self.shape:
            raise ValueError("Invalid pinned RGB input")
        np.copyto(self.array, frame)
        return self.array

    def close(self):
        pointer, self.pointer = self.pointer, None
        self.array = self._owner = None
        if pointer is not None:
            _cuda(cudart.cudaFreeHost(pointer))


class PinnedInputMixin:
    """Stage the full RGB input through one reusable page-locked buffer."""

    def __init__(self, width, height, policy, engine, **kwargs):
        super().__init__(width, height, policy, engine, **kwargs)
        self.pinned_input = None
        try:
            self.pinned_input = PinnedRgbBuffer((height, width, 3))
        except BaseException as primary:
            try:
                super().close()
            except Exception as cleanup:
                primary.add_note(str(cleanup))
            raise

    def render(self, frame, depth, *, diagnostic=False, scene=None):
        self._owner()
        started = time.perf_counter_ns()
        pinned = self.pinned_input.copy(frame)
        copied = time.perf_counter_ns()
        # The incoming observation refers to the pageable frame. Re-observe the
        # exact copy so the base ownership contract remains identity-based.
        pinned_scene = self.scene_history.inspect(pinned)
        if scene is not None and pinned_scene.cut != scene.cut:
            raise RuntimeError("Pinned input changed the scene-cut decision")
        result = super().render(
            pinned, depth, diagnostic=diagnostic, scene=pinned_scene
        )
        self.last["input_stage_ms"] = (copied - started) / 1e6
        return result

    def close(self):
        if threading.get_ident() != self.thread:
            raise RuntimeError("GPU candidate close from another thread")
        errors = []
        try:
            super().close()
        except Exception as error:
            errors.append(error)
        pinned, self.pinned_input = self.pinned_input, None
        if pinned is not None:
            try:
                pinned.close()
            except Exception as error:
                errors.append(error)
        if errors:
            primary = errors[0]
            for cleanup in errors[1:]:
                primary.add_note(str(cleanup))
            raise primary


class LiveGpuPinnedCandidate(PinnedInputMixin, LiveGpuCandidate):
    """Host-output candidate used only for exact numerical validation."""


class LiveGpuPinnedTexture(PinnedInputMixin, LiveGpuTexture):
    """Native texture candidate used for actual live validation."""
