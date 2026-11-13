"""Live-only screen-plane tracking; bounded state, no model or UI dependencies."""
import math

import numpy as np


class DepthRangeClock:
    """Source elapsed time, with explicit discontinuity reset and bounded state."""

    def __init__(self):
        self.source_ns = None

    def update(self, source_ns, *, reset=False):
        if source_ns is not None and (type(source_ns) is not int or source_ns <= 0):
            raise ValueError('Invalid depth-range source timestamp')
        dt = 1 / 60
        if self.source_ns is not None and source_ns is not None:
            dt = (source_ns - self.source_ns) / 1e9
            if not 0 < dt <= .1:
                reset, dt = True, 1 / 60
        elif self.source_ns is not None or source_ns is not None:
            reset = True
        self.source_ns = source_ns
        return dt, reset


class ScreenPlane:
    """Anchor a central depth statistic without chasing every inference fluctuation.

    The initial scene can choose its plane immediately. Within a scene, a depth
    deadband, one-second response and a speed bound prevent global stereo jumps.
    This is a content anchor, not gaze tracking or physical display calibration.
    """

    def __init__(self):
        self.value = None
        self.source_ns = None

    def update(self, samples, source_ns=None, *, reset=False):
        samples = np.asarray(samples)
        if samples.shape != (32, 32) or not np.isfinite(samples).all():
            raise ValueError("Invalid stereo depth samples")
        center = samples[8:24, 8:24]
        target = float(np.clip(np.quantile(center, .65), .25, .80))
        if source_ns is not None and (type(source_ns) is not int or source_ns <= 0):
            raise ValueError("Invalid stereo source timestamp")
        dt = 1 / 60
        if source_ns is not None and self.source_ns is not None:
            dt = (source_ns - self.source_ns) / 1e9
            if not 0 < dt <= .1:
                reset = True
        if reset or self.value is None:
            self.value = target
        else:
            delta = target - self.value
            if abs(delta) > .025:
                delta -= math.copysign(.025, delta)
                step = delta * -math.expm1(-dt)
                self.value += float(np.clip(step, -.06 * dt, .06 * dt))
        self.source_ns = source_ns
        return self.value


def sample_depth(depth):
    """Same point-sampling coordinates as the native 32x32 diagnostic kernel."""
    height, width = depth.shape
    y = np.minimum((np.arange(32) * 2 + 1) * height // 64, height - 1)
    x = np.minimum((np.arange(32) * 2 + 1) * width // 64, width - 1)
    return np.ascontiguousarray(depth[np.ix_(y, x)], dtype=np.float32)
