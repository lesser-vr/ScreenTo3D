"""Bounded future-aware depth fusion for file-only Offline Quality jobs."""

from collections import deque
from dataclasses import dataclass

import cv2
import numpy as np


def is_scene_cut(previous, current, threshold):
    """Match Offline Quality's file-only cut predicate at fixed cost."""
    if (
        not isinstance(previous, np.ndarray)
        or not isinstance(current, np.ndarray)
        or previous.dtype != np.uint8
        or current.dtype != np.uint8
        or previous.ndim != 3
        or current.ndim != 3
        or previous.shape[2:] != (3,)
        or current.shape[2:] != (3,)
        or min(*previous.shape[:2], *current.shape[:2]) < 1
        or not 0.0 < threshold <= 1.0
    ):
        raise ValueError("Invalid offline scene-cut input")
    old = cv2.resize(previous, (32, 32)).astype(np.float32)
    new = cv2.resize(current, (32, 32)).astype(np.float32)
    return float(np.mean(np.abs(new - old))) / 255.0 > threshold


@dataclass(frozen=True)
class _Sample:
    index: int
    frame: np.ndarray | None
    guide: np.ndarray
    depth: np.ndarray
    normalized: np.ndarray
    low: float
    high: float


class CenteredDepthWindow:
    """Emit ordered frames after a bounded, scene-local lookahead.

    VDA remains the depth model. This processor aligns each nearby observation
    to the target frame's robust depth range, then uses only color/depth-stable
    pixels from past and future observations. It deliberately does not warp
    moving content without motion vectors.
    """

    strategy = "centered-color-gated-depth-fusion-v1"

    def __init__(
        self,
        radius=2,
        *,
        max_working_width=960,
        color_threshold=0.04,
        depth_threshold=0.10,
    ):
        if type(radius) is not int or not 1 <= radius <= 8:
            raise ValueError("Offline depth radius must be an integer from 1 to 8")
        if type(max_working_width) is not int or not 64 <= max_working_width <= 4096:
            raise ValueError("Invalid offline depth working width")
        if not 0.0 < color_threshold <= 1.0 or not 0.0 < depth_threshold <= 1.0:
            raise ValueError("Invalid offline depth stability threshold")
        self.radius = radius
        self.max_working_width = max_working_width
        self.color_threshold = float(color_threshold)
        self.depth_threshold = float(depth_threshold)
        self.history = deque(maxlen=radius)
        self.pending = deque()
        self.next_index = 0
        self.submitted = self.emitted = self.future_context_frames = 0
        self.scenes = self.cut_flushes = 0
        self.max_resident_samples = self.max_resident_bytes = 0
        self.closed = False

    @property
    def capacity(self):
        return self.radius * 2 + 1

    def _check_open(self):
        if self.closed:
            raise RuntimeError("Offline depth window is closed")

    def _sample(self, frame, depth):
        if (
            not isinstance(frame, np.ndarray)
            or frame.dtype != np.uint8
            or frame.ndim != 3
            or frame.shape[2] != 3
        ):
            raise ValueError("Offline depth requires uint8 RGB frames")
        if (
            not isinstance(depth, np.ndarray)
            or depth.dtype != np.float32
            or depth.ndim != 3
            or depth.shape[0] != 1
            or not np.isfinite(depth).all()
        ):
            raise ValueError("Offline depth requires finite float32 [1,H,W]")
        height, width = frame.shape[:2]
        working_width = min(width, self.max_working_width)
        working_height = max(1, round(height * working_width / width))
        size = (working_width, working_height)
        guide = cv2.resize(frame, size, interpolation=cv2.INTER_AREA)
        working_depth = cv2.resize(
            depth[0], size, interpolation=cv2.INTER_LINEAR
        ).astype(np.float32, copy=False)
        working_depth = np.ascontiguousarray(working_depth)
        normalized, low, high = self._normalized(working_depth)
        return _Sample(
            self.next_index,
            frame.copy(),
            np.ascontiguousarray(guide),
            working_depth,
            np.ascontiguousarray(normalized),
            low,
            high,
        )

    @staticmethod
    def _normalized(depth):
        low, high = np.percentile(depth, (2.0, 98.0)).astype(np.float32)
        span = float(high - low)
        if span <= 1.0e-6:
            return np.zeros_like(depth), float(low), float(high)
        return np.clip((depth - low) / span, 0.0, 1.0), float(low), float(high)

    def _fuse(self, target, candidates):
        target_normalized, low, high = target.normalized, target.low, target.high
        accumulated = target_normalized.copy()
        weights = np.ones_like(target_normalized)
        used_future = False
        for candidate in candidates:
            distance = abs(candidate.index - target.index)
            if distance == 0:
                continue
            normalized = candidate.normalized
            color_delta = (
                np.mean(
                    np.abs(candidate.guide.astype(np.float32) - target.guide), axis=2
                )
                / 255.0
            )
            depth_delta = np.abs(normalized - target_normalized)
            color_weight = np.clip(1.0 - color_delta / self.color_threshold, 0.0, 1.0)
            depth_weight = np.clip(1.0 - depth_delta / self.depth_threshold, 0.0, 1.0)
            temporal_weight = 1.0 / (distance + 1.0)
            weight = (color_weight * depth_weight * temporal_weight).astype(
                np.float32, copy=False
            )
            accumulated += normalized * weight
            weights += weight
            used_future |= candidate.index > target.index and bool(np.any(weight))
        fused = accumulated / weights
        if high - low > 1.0e-6:
            fused = fused * (high - low) + low
        else:
            fused = target.depth.copy()
        self.future_context_frames += int(used_future)
        return np.ascontiguousarray(fused[None].astype(np.float32, copy=False))

    def _resident_bytes(self):
        total = 0
        for sample in (*self.history, *self.pending):
            total += (
                sample.guide.nbytes + sample.depth.nbytes + sample.normalized.nbytes
            )
            if sample.frame is not None:
                total += sample.frame.nbytes
        return total

    def _observe_bounds(self):
        resident = len(self.history) + len(self.pending)
        if resident > self.capacity:
            raise RuntimeError("Offline depth window exceeded its fixed capacity")
        self.max_resident_samples = max(self.max_resident_samples, resident)
        self.max_resident_bytes = max(self.max_resident_bytes, self._resident_bytes())

    def _emit_one(self):
        target = self.pending[0]
        candidates = list(self.history) + list(self.pending)[: self.radius + 1]
        depth = self._fuse(target, candidates)
        target = self.pending.popleft()
        if target.frame is None:
            raise RuntimeError("Pending offline frame lost ownership")
        self.history.append(
            _Sample(
                target.index,
                None,
                target.guide,
                target.depth,
                target.normalized,
                target.low,
                target.high,
            )
        )
        self.emitted += 1
        self._observe_bounds()
        return target.frame, depth

    def _drain(self):
        output = []
        while self.pending:
            output.append(self._emit_one())
        return output

    def submit(self, frame, depth, *, cut_before=False):
        self._check_open()
        if type(cut_before) is not bool:
            raise ValueError("cut_before must be boolean")
        output = []
        if cut_before:
            output.extend(self._drain())
            self.history.clear()
            self.cut_flushes += 1
        if not self.history and not self.pending:
            self.scenes += 1
        sample = self._sample(frame, depth)
        self.next_index += 1
        self.submitted += 1
        self.pending.append(sample)
        self._observe_bounds()
        if len(self.pending) > self.radius:
            output.append(self._emit_one())
        return output

    def finish(self):
        self._check_open()
        output = self._drain()
        self.history.clear()
        self.closed = True
        if self.emitted != self.submitted:
            raise RuntimeError("Offline depth window did not emit every frame")
        return output

    def telemetry(self):
        return {
            "enabled": True,
            "strategy": self.strategy,
            "radius": self.radius,
            "window_frames": self.capacity,
            "lookahead_frames": self.radius,
            "max_working_width": self.max_working_width,
            "color_threshold": self.color_threshold,
            "depth_threshold": self.depth_threshold,
            "submitted_frames": self.submitted,
            "emitted_frames": self.emitted,
            "future_context_frames": self.future_context_frames,
            "scenes": self.scenes,
            "cut_flushes": self.cut_flushes,
            "max_resident_samples": self.max_resident_samples,
            "max_resident_bytes": self.max_resident_bytes,
            "bounded": True,
            "motion_warp": False,
        }
