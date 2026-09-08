"""Source-resolution device depth through the owned live CUDA consumer."""

import ctypes as ct

from .live_gpu_candidate import LiveGpuCandidate


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
        profile = getattr(self.engine, "profile", None)
        if (
            not isinstance(profile, tuple)
            or len(profile) != 2
            or not all(type(value) is int and value > 0 for value in profile)
        ):
            raise ValueError("Source-depth engine profile is unavailable")
        depth = self.engine.infer_device(frame)
        depth.validate()
        if depth.owner is not self.engine or depth.stream != self._stream(self.engine):
            raise ValueError("Depth belongs to another engine or CUDA stream")
        self.h2d += 3 * profile[0] * profile[1] * 4
        return depth

    def _validate_frame(self, frame):
        if frame.dtype.name != "uint8" or frame.shape != (
            self.height,
            self.width,
            3,
        ):
            raise ValueError("Invalid inference RGB frame")

    def _post(self, frame, depth, aligned, reset):
        self._check(
            self.dll.live_post_source(
                self.handle,
                frame.ctypes.data,
                depth.pointer,
                1,
                self.policy.depth_guide_radius,
                self.policy.temporal_alpha,
                self.policy.temporal_color_threshold,
                self.policy.temporal_depth_threshold,
                int(reset),
                aligned.ctypes.data if aligned is not None else None,
                self.policy.temporal_depth_transition,
            )
        )
        self.h2d += frame.nbytes
