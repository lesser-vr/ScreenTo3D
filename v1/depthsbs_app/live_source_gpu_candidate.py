"""Source-resolution device depth through the owned live CUDA consumer."""

import ctypes as ct

from .live_gpu_candidate import LiveGpuCandidate
from .gpu_frame import GpuFrame


class LiveSourceGpuCandidate(LiveGpuCandidate):
    """Keep an explicit model's source-sized depth on its owner CUDA stream."""

    def __init__(self, width, height, policy, engine):
        super().__init__(width, height, policy, engine)
        self.dll.live_post_source.argtypes = [
            ct.c_void_p,
            ct.c_void_p,
            ct.c_void_p,
            ct.c_int,
            ct.c_int,
            ct.c_double,
            ct.c_float,
            ct.c_float,
            ct.c_int,
            ct.c_void_p,
            ct.c_double,
        ]

    def infer(self, frame):
        self._owner()
        self._validate_frame(frame)
        expected_input_bytes = self._input_bytes()
        depth = self.engine.infer_device(frame)
        depth.validate()
        if depth.owner is not self.engine or depth.stream != self._stream(self.engine):
            raise ValueError("Depth belongs to another engine or CUDA stream")
        input_bytes = getattr(self.engine, 'last_input_bytes', None)
        self.h2d += expected_input_bytes if input_bytes is None else input_bytes
        return depth

    def _input_bytes(self):
        profile = getattr(self.engine, "profile", None)
        if (
            isinstance(profile, tuple)
            and len(profile) == 2
            and all(type(value) is int and value > 0 for value in profile)
        ):
            return 3 * profile[0] * profile[1] * 4
        shape = getattr(self.engine, "input_shape", None)
        if (
            isinstance(shape, tuple)
            and len(shape) == 5
            and shape[:3] == (1, 1, 3)
            and all(type(value) is int and value > 0 for value in shape)
        ):
            return shape[-2] * shape[-1] * 3 * 4
        raise ValueError("Source-depth engine profile is unavailable")

    def _validate_frame(self, frame):
        if frame.dtype.name != "uint8" or frame.shape != (
            self.height,
            self.width,
            3,
        ):
            raise ValueError("Invalid inference RGB frame")

    def _post(self, frame, depth, aligned, reset):
        gpu_frame = isinstance(frame, GpuFrame)
        if gpu_frame:
            frame.validate(self.engine)
        self._check(
            self.dll.live_post_source(
                self.handle,
                frame.rgb.data_ptr() if gpu_frame else frame.ctypes.data,
                depth.pointer,
                2 if gpu_frame else 1,
                self.policy.depth_guide_radius,
                self.policy.temporal_alpha,
                self.policy.temporal_color_threshold,
                self.policy.temporal_depth_threshold,
                int(reset),
                aligned.ctypes.data if aligned is not None else None,
                self.policy.temporal_depth_transition,
            )
        )
        if not gpu_frame:
            self.h2d += frame.nbytes
