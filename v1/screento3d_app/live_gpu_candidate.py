"""Pinned local GPU postprocessing; SM120 desktop default, not a public release."""

import ctypes as ct
import hashlib
import os
import threading
import time
import cv2
import numpy as np
from .desktop_jobs import ROOT
from .live_scene_history import LiveSceneHistory
from .gpu_frame import GpuFrame
from .portable_cuda import binary

DLL_SHA256 = "0394a7b790c92db37aaa49190e213edc65914e79625f03d38d62cf3c2911da85"
DLL_PATH = ROOT / "out/static-sbs/live_depth.dll"
DEFAULT_RESOLVE = "parallel"


from .environment import get as app_env

class LiveGpuCandidate:
    library_path = DLL_PATH
    library_sha256 = DLL_SHA256

    def __init__(self, width, height, policy, engine):
        if not (16 <= width <= 4096 and 16 <= height <= 2160):
            raise ValueError("Invalid live dimensions")
        if not 0 <= policy.temporal_depth_transition <= policy.temporal_depth_threshold:
            raise ValueError("Invalid live temporal transition")
        self.resolve_impl = app_env("SCREENTO3D_LIVE_RESOLVE", DEFAULT_RESOLVE)
        if self.resolve_impl not in ("serial", "parallel"):
            raise ValueError("SCREENTO3D_LIVE_RESOLVE must be serial or parallel")
        self._engine_check(engine)
        from .trt_backend import _cuda, cudart

        properties = _cuda(
            cudart.cudaGetDeviceProperties(_cuda(cudart.cudaGetDevice()))
        )
        path, expected_hash = binary(self.library_path, self.library_sha256)
        arch = properties.major, properties.minor
        if arch < (7, 5) or (path == self.library_path and arch != (12, 0)):
            raise RuntimeError(
                "The installed live CUDA renderer does not support this GPU architecture"
            )
        self.engine, self.policy = engine, policy
        self.width, self.height = width, height
        self.thread = threading.get_ident()
        self.failed = False
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
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
        self.gpu_refinements = 0
        self.flat_background = None
        self.background_color = None
        self.last = {}
        self.small_rgb = None
        self.gpu_ms = np.zeros(8, np.float32)
        self.projection_ms = np.zeros(6, np.float32)
        self.last_generation = None
        self.stereo_quality = "reference"
        self.stereo_convergence = policy.convergence
        self.source_ns = None
        self.same_input = False
        self.static_capable = hasattr(self.dll, 'live_set_same_input')
        if self.static_capable:
            self.dll.live_set_same_input.argtypes = [ct.c_void_p, ct.c_int]
        self.screen_plane = None
        self.stereo_samples = None
        self.range_clock = None
        self.motion_history = None
        self.window_clock = None

    def configure_live_quality(self, mode):
        """Explicit worker-owned policy; ordinary file/model oracles stay reference."""
        self._owner()
        if mode not in ("reference", "anchor", "subpixel", "stable", "coverage", "range", "motion", "window", "budget", "detail"):
            raise ValueError("Invalid stereo quality setting")
        from .stereo_stability import ScreenPlane, DepthRangeClock
        self.dll.live_set_subpixel.argtypes = [ct.c_void_p, ct.c_int]
        self.dll.live_set_coverage.argtypes = [ct.c_void_p, ct.c_int]
        self.dll.live_stereo_samples.argtypes = [ct.c_void_p, ct.c_void_p]
        self._check(self.dll.live_set_subpixel(self.handle, int(mode in ("stable", "subpixel", "coverage", "range", "motion", "window", "budget", "detail"))))
        self._check(self.dll.live_set_coverage(self.handle, int(mode in ("coverage", "range", "motion", "window", "budget", "detail"))))
        self.dll.live_set_disparity_budget.argtypes = [ct.c_void_p, ct.c_int]
        self._check(self.dll.live_set_disparity_budget(self.handle, int(mode in ("budget", "detail"))))
        self.dll.live_set_detail.argtypes = [ct.c_void_p, ct.c_int]
        self._check(self.dll.live_set_detail(self.handle, 3 if mode == "detail" else 0))
        self.dll.live_set_range_dt.argtypes = [ct.c_void_p, ct.c_double]
        self._check(self.dll.live_set_range_dt(self.handle, -1))
        self.range_clock = DepthRangeClock() if mode in ("range", "motion", "window", "budget", "detail") else None
        self.dll.live_set_window.argtypes = [ct.c_void_p,ct.c_double,ct.c_int]
        self._check(self.dll.live_set_window(self.handle,-1,1))
        self.window_clock = DepthRangeClock() if mode in ("window", "budget", "detail") else None
        if self.motion_history is not None:
            self.motion_history.close()
            self.motion_history = None
        if mode in ("motion", "window", "budget", "detail"):
            from .motion_history import MotionHistory
            self.motion_history = MotionHistory(self.width,self.height,self._stream(self.engine),self.library_sha256)
        self.reset_pending = True
        self.stereo_quality = mode
        self.screen_plane = ScreenPlane() if mode in ("stable", "anchor") else None
        self.stereo_samples = np.empty((32, 32), np.float32) if self.screen_plane else None
        self.stereo_convergence = self.policy.convergence

    def _update_screen_plane(self, refined, reset):
        if self.screen_plane is None:
            return
        if refined is None:
            self._check(self.dll.live_stereo_samples(self.handle, self.stereo_samples.ctypes.data))
            self.d2h += self.stereo_samples.nbytes
            self.syncs += 1
            samples = self.stereo_samples
        else:
            from .stereo_stability import sample_depth
            samples = sample_depth(refined)
        self.stereo_convergence = self.screen_plane.update(samples, self.source_ns, reset=reset)

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
        if check is None:
            check = getattr(engine, "_check", None)
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

    def hold_static(self, scene):
        """Content history is stationary; keep the clocks on the capture timeline."""
        for clock in (self.range_clock, self.window_clock, self.motion_history.clock):
            clock.update(self.source_ns)
        self.scene_history.commit(scene)

    def set_same_input(self, same):
        if same != self.same_input:
            self._check(self.dll.live_set_same_input(self.handle, int(same)))
            self.same_input = same

    def needs_background(self, frame):
        if not self.policy.flat_background_refinement:
            return False
        border = frame.border() if isinstance(frame, GpuFrame) else np.concatenate((frame[0], frame[-1], frame[:, 0], frame[:, -1]))
        color = np.median(border, axis=0).astype(np.float32)
        self.background_color = color
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
        if isinstance(frame, GpuFrame):
            frame.validate(self.engine)
        else:
            frame = np.ascontiguousarray(frame)
        reset = self.reset_pending or scene.cut
        if self.range_clock is not None:
            dt, reset = self.range_clock.update(self.source_ns, reset=reset)
            self._check(self.dll.live_set_range_dt(self.handle, dt))
        background = self.needs_background(frame)
        aligned = (
            np.empty((self.height, self.width), np.float32)
            if diagnostic
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
        background_applied = False
        if background:
            from .flat_background_gpu import FlatBackground, color_bounds
            bounds = color_bounds(self.background_color, self.policy.flat_background_tolerance)
            if bounds is not None:
                try:
                    if self.flat_background is None:
                        self.flat_background = FlatBackground(self.width, self.height, self._stream(self.engine), self.library_sha256)
                    background_applied = self.flat_background.apply(self.handle, bounds,
                        self.policy.flat_background_min_coverage, self.policy.depth_guide_radius)
                    self.d2h += self.flat_background.readback_bytes
                    self.syncs += self.flat_background.syncs
                    self.gpu_refinements += int(background_applied)
                except Exception:
                    self.failed = True
                    raise
        background_end = time.perf_counter_ns()
        self._update_screen_plane(refined, reset)
        if self.motion_history is not None:
            if background_applied:
                self.motion_history.invalidate()
            else:
                # A confirmed RGB repeat has zero displacement. Refresh the
                # optical-flow reference for the first moving frame.
                self.motion_history.apply(self.handle,self.source_ns,reset=reset or self.same_input)
                if diagnostic:
                    self.motion_history.read_depth(self.handle,aligned)
                    self.d2h += aligned.nbytes
                    self.syncs += 1
        if self.window_clock is not None:
            dt, window_reset = self.window_clock.update(self.source_ns,reset=reset)
            self._check(self.dll.live_set_window(self.handle,dt,int(window_reset)))
        projected = self._project(frame, refined)
        self.engine.complete_device(depth)
        self._read_projection_times()
        # Timings are stream intervals including enqueue gaps, not GPU utilization.
        if self.small_rgb is not None:
            self._check(self.dll.live_times(self.handle, self.gpu_ms.ctypes.data))
            if self.last_generation == depth.generation:
                self.gpu_ms[:2] = 0
        self.last_generation = depth.generation
        self.reset_pending = False
        self.scene_history.commit(scene)
        if isinstance(frame, GpuFrame):
            self.d2h += frame.readback_bytes
            self.syncs += frame.readback_syncs
            frame.readback_bytes = frame.readback_syncs = 0
        self.frames += 1
        self.last = dict(
            post_submit_ms=(post - started) / 1e6,
            background_ms=(background_end - post) / 1e6,
            project_wait_ms=(time.perf_counter_ns() - background_end) / 1e6,
            stereo_convergence=self.stereo_convergence,
            stereo_quality=self.stereo_quality,
        )
        result = self._pack_result(projected)
        return (result, aligned) if diagnostic else result

    def _read_projection_times(self):
        self._check(self.dll.live_projection_times(self.handle, self.projection_ms.ctypes.data))

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
        left, right = np.empty(frame.shape, np.uint8), np.empty(frame.shape, np.uint8)
        invalid = ct.c_int()
        self._check(
            self.dll.live_project(
                self.handle,
                refined.ctypes.data if refined is not None else None,
                self.stereo_convergence,
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
        errors = []
        if getattr(self, 'flat_background', None) is not None:
            try:
                self.flat_background.close()
            except Exception as error:
                errors.append(error)
            self.flat_background = None
        if self.motion_history is not None:
            try:
                self.motion_history.close()
            except Exception as error:
                errors.append(error)
            self.motion_history = None
        handle, self.handle = self.handle, ct.c_void_p()
        try:
            if handle.value:
                self._check(self.dll.live_destroy(handle))
        except Exception as error:
            errors.append(error)
        self.small_rgb = None
        self.scene_history.reset()
        if errors:
            for error in errors[1:]:
                errors[0].add_note(str(error))
            raise errors[0]

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
