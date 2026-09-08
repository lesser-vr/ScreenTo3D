"""Pinned local GPU postprocessing; SM120 desktop default, not a public release."""

import ctypes as ct
import hashlib
import os
import threading
import time
import cv2
import numpy as np
from .desktop_jobs import ROOT
from .stereo import refine_flat_background
from .live_scene_history import LiveSceneHistory

DLL_SHA256 = "ad0871cce22011926b0948a59368ae1f71d9727962160110bdea7974f5e296eb"
DLL_PATH = ROOT / "out/live-depth-parallel/live_depth.dll"
DEFAULT_RESOLVE = "parallel"


class LiveGpuCandidate:
    def __init__(self, width, height, policy, engine):
        if not (16 <= width <= 4096 and 16 <= height <= 2160):
            raise ValueError("Invalid live dimensions")
        if not 0 <= policy.temporal_depth_transition <= policy.temporal_depth_threshold:
            raise ValueError("Invalid live temporal transition")
        self.resolve_impl = os.environ.get("DEPTHSBS_LIVE_RESOLVE", DEFAULT_RESOLVE)
        if self.resolve_impl not in ("serial", "parallel"):
            raise ValueError("DEPTHSBS_LIVE_RESOLVE must be serial or parallel")
        self._engine_check(engine)
        from .trt_backend import _cuda, cudart

        properties = _cuda(
            cudart.cudaGetDeviceProperties(_cuda(cudart.cudaGetDevice()))
        )
        if (properties.major, properties.minor) != (12, 0):
            raise RuntimeError(
                "This local GPU candidate requires compute capability 12.0"
            )
        self.engine, self.policy = engine, policy
        self.width, self.height = width, height
        self.thread = threading.get_ident()
        self.failed = False
        path = DLL_PATH
        if hashlib.sha256(path.read_bytes()).hexdigest() != DLL_SHA256:
            raise ValueError("GPU candidate DLL checksum mismatch")
        self.dll = ct.CDLL(str(path))
        self.dll.live_create.argtypes = [
            ct.POINTER(ct.c_void_p),
            ct.c_int,
            ct.c_int,
            ct.c_void_p,
        ]
        self.dll.live_destroy.argtypes = [ct.c_void_p]
        self.dll.live_prepare.argtypes = [ct.c_void_p] * 3
        self.dll.live_times.argtypes = [ct.c_void_p] * 2
        self.dll.live_projection_times.argtypes = [ct.c_void_p] * 2
        self.dll.live_set_parallel.argtypes = [ct.c_void_p, ct.c_int]
        self.dll.live_post.argtypes = [ct.c_void_p] * 3 + [
            ct.c_int,
            ct.c_double,
            ct.c_float,
            ct.c_float,
            ct.c_int,
            ct.c_void_p,
            ct.c_double,
        ]
        self.dll.live_project.argtypes = (
            [ct.c_void_p] * 2 + [ct.c_float, ct.c_float, ct.c_int] + [ct.c_void_p] * 3
        )
        self.handle = ct.c_void_p()
        self._check(
            self.dll.live_create(
                ct.byref(self.handle), width, height, self._stream(engine)
            )
        )
        self._check(
            self.dll.live_set_parallel(
                self.handle, int(self.resolve_impl == "parallel")
            )
        )
        self.scene_history = LiveSceneHistory(policy.scene_cut_threshold)
        self.reset_pending = True
        self.h2d = self.d2h = self.syncs = self.frames = 0
        self.cpu_refinements = 0
        self.last = {}
        self.small_rgb = None
        self.gpu_ms = np.zeros(8, np.float32)
        self.projection_ms = np.zeros(6, np.float32)
        self.last_generation = None

    def infer(self, frame):
        self._owner()
        if frame.dtype != np.uint8 or frame.shape != (self.height, self.width, 3):
            raise ValueError("Invalid inference RGB frame")
        # Keep OpenCV's exact uint8 cubic resize; normalization/layout is CUDA.
        self.small_rgb = cv2.resize(frame, (518, 518), interpolation=cv2.INTER_CUBIC)

        def prepare(pointer, stream):
            if stream != self._stream(self.engine):
                raise ValueError("Unexpected input stream")
            self._check(
                self.dll.live_prepare(self.handle, self.small_rgb.ctypes.data, pointer)
            )
            self.h2d += self.small_rgb.nbytes

        return self.engine.infer_prepared_device(prepare)

    def _check(self, code):
        if code:
            self.failed = True
            raise RuntimeError(f"GPU candidate CUDA failure: {code}")

    def _owner(self):
        if threading.get_ident() != self.thread:
            raise RuntimeError("GPU candidate used from another thread")
        if not self.handle.value:
            raise RuntimeError("GPU candidate closed")
        if self.failed:
            raise RuntimeError("GPU candidate failed; create a new session")
        self._engine_check(self.engine)

    @staticmethod
    def _engine_check(engine):
        check = getattr(engine, "_device_check", None)
        if check is None:
            check = getattr(engine, "check", None)
        if not callable(check):
            raise TypeError("GPU depth engine must expose an owner/device check")
        check()

    @staticmethod
    def _stream(engine):
        stream = engine.stream
        return int(getattr(stream, "cuda_stream", stream))

    def reset(self):
        self._owner()
        self.reset_pending = True
        self.scene_history.reset()

    def is_scene_cut(self, frame):
        return self.inspect_scene(frame).cut

    def inspect_scene(self, frame):
        self._owner()
        return self.scene_history.inspect(frame)

    def needs_background(self, frame):
        if not self.policy.flat_background_refinement:
            return False
        border = np.concatenate((frame[0], frame[-1], frame[:, 0], frame[:, -1]))
        color = np.median(border, axis=0).astype(np.float32)
        return (
            np.mean(
                np.max(np.abs(border.astype(np.float32) - color), axis=1)
                <= self.policy.flat_background_tolerance * 255
            )
            >= 0.98
        )

    def render(self, frame, depth, *, diagnostic=False, scene=None):
        self._owner()
        depth.validate()
        if depth.owner is not self.engine:
            raise ValueError("Depth belongs to another engine")
        if frame.dtype != np.uint8 or frame.shape != (self.height, self.width, 3):
            raise ValueError("Invalid RGB frame")
        if scene is None:
            scene = self.scene_history.inspect(frame)
        self.scene_history.validate(scene, frame)
        frame = np.ascontiguousarray(frame)
        reset = self.reset_pending or scene.cut
        background = self.needs_background(frame)
        aligned = (
            np.empty((self.height, self.width), np.float32)
            if background or diagnostic
            else None
        )
        started = time.perf_counter_ns()
        self._post(frame, depth, aligned, reset)
        refined = None
        if aligned is not None:
            from .trt_backend import _cuda, cudart

            _cuda(cudart.cudaStreamSynchronize(self._stream(self.engine)))
            self.syncs += 1
            self.d2h += aligned.nbytes
            if not np.isfinite(aligned).all():
                self.failed = True
                raise RuntimeError("Non-finite GPU aligned depth")
        post = time.perf_counter_ns()
        if background:
            refined = refine_flat_background(
                frame,
                aligned,
                tolerance=self.policy.flat_background_tolerance,
                minimum_coverage=self.policy.flat_background_min_coverage,
                radius=self.policy.depth_guide_radius,
            )
            if refined is aligned:
                refined = None
            else:
                self.cpu_refinements += 1
                self.h2d += refined.nbytes
        background_end = time.perf_counter_ns()
        projected = self._project(frame, refined)
        self.engine.complete_device(depth)
        self._check(
            self.dll.live_projection_times(self.handle, self.projection_ms.ctypes.data)
        )
        # Timings are stream intervals including enqueue gaps, not GPU utilization.
        if self.small_rgb is not None:
            self._check(self.dll.live_times(self.handle, self.gpu_ms.ctypes.data))
            if self.last_generation == depth.generation:
                self.gpu_ms[:2] = 0
        self.last_generation = depth.generation
        self.reset_pending = False
        self.scene_history.commit(scene)
        self.frames += 1
        self.last = dict(
            post_submit_ms=(post - started) / 1e6,
            background_ms=(background_end - post) / 1e6,
            project_wait_ms=(time.perf_counter_ns() - background_end) / 1e6,
        )
        result = self._pack_result(projected)
        return (result, aligned) if diagnostic else result

    def _post(self, frame, depth, aligned, reset):
        self._check(
            self.dll.live_post(
                self.handle,
                frame.ctypes.data,
                depth.pointer,
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

    def _project(self, frame, refined):
        """Default host output; texture delivery overrides only this boundary."""
        left, right = np.empty_like(frame), np.empty_like(frame)
        invalid = ct.c_int()
        self._check(
            self.dll.live_project(
                self.handle,
                refined.ctypes.data if refined is not None else None,
                self.policy.convergence,
                max(1.0, self.width * self.policy.divergence),
                int(self.policy.conservative_stereo_coverage),
                left.ctypes.data,
                right.ctypes.data,
                ct.byref(invalid),
            )
        )
        self.syncs += 1
        self.d2h += left.nbytes + right.nbytes + 4
        if invalid.value:
            self.failed = True
            raise RuntimeError("Non-finite raw GPU depth")
        return left, right

    def _pack_result(self, projected):
        return np.concatenate(projected, axis=1)

    def close(self):
        if threading.get_ident() != self.thread:
            raise RuntimeError("GPU candidate close from another thread")
        handle, self.handle = self.handle, ct.c_void_p()
        if handle.value:
            self._check(self.dll.live_destroy(handle))
        self.small_rgb = None
        self.scene_history.reset()

    def __enter__(self):
        self._owner()
        return self

    def __exit__(self, kind, primary, tb):
        try:
            self.close()
        except Exception as error:
            if primary is None:
                raise
            primary.add_note(str(error))
