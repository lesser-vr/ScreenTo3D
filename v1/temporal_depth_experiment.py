"""One-frame motion-aligned depth history prototype, never enabled by default.

One monocular result feeds both eyes. No recurrent filtered history, frame skipping,
or invented geometry: unreliable history falls back exactly to current depth.
"""
import cv2
import numpy as np


def align_history(current, previous, gray, previous_gray, forward, backward, weight=.35):
    shape = current.shape
    if not (current.dtype == previous.dtype == np.float32 and previous.shape == shape
            and gray.shape == previous_gray.shape == shape
            and forward.shape == backward.shape == (*shape, 2)
            and np.isfinite(current).all() and np.isfinite(previous).all()
            and np.isfinite(forward).all() and np.isfinite(backward).all()
            and 0 <= weight <= .5):
        raise ValueError('Invalid motion/depth contract')
    h, w = shape
    y, x = np.indices(shape, dtype=np.float32)
    mx, my = x + backward[..., 0], y + backward[..., 1]
    inside = (mx >= 0) & (my >= 0) & (mx < w-1) & (my < h-1)
    old = cv2.remap(previous, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    old_gray = cv2.remap(previous_gray, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    reverse = cv2.remap(forward, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    consistency = np.linalg.norm(reverse + backward, axis=2)
    photo = np.abs(gray.astype(np.float32)-old_gray.astype(np.float32))/255
    delta = np.abs(current-old)
    # Do not interpolate history across thin silhouettes/depth discontinuities.
    kernel = np.ones((3, 3), np.uint8)
    edge = (cv2.dilate(current, kernel)-cv2.erode(current, kernel) > .03)
    edge |= (cv2.dilate(old, kernel)-cv2.erode(old, kernel) > .03)
    edge = cv2.dilate(edge.astype(np.uint8), kernel) != 0
    valid = inside & ~edge & (consistency < 1.) & (photo < .06) & (delta < .08)
    confidence = (np.clip(1-consistency, 0, 1) * np.clip(1-photo/.06, 0, 1)
                  * np.clip(1-delta/.08, 0, 1)).astype(np.float32)
    blend = np.float32(weight) * confidence
    result = np.where(valid, current + blend*(old-current), current).astype(np.float32)
    return result, valid


class MotionDepth:
    """Own only the previous unfiltered depth/RGB grid; history age <= 50ms."""
    def __init__(self):
        self.previous = self.gray = self.sequence = self.timestamp = self.source_shape = None
        self.forward = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_FAST)
        self.backward = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_FAST)

    def reset(self):
        self.previous = self.gray = self.sequence = self.timestamp = self.source_shape = None

    def update(self, frame, depth, sequence, timestamp_ns, *, cut=False):
        if (not isinstance(frame, np.ndarray) or frame.dtype != np.uint8
                or frame.ndim != 3 or frame.shape[2] != 3
                or not 16 <= frame.shape[0] <= 2160 or not 16 <= frame.shape[1] <= 4096
                or not isinstance(depth, np.ndarray) or depth.dtype != np.float32 or depth.ndim != 2
                or not all(32 <= size <= 1024 for size in depth.shape)
                or not np.isfinite(depth).all() or depth.min() < 0 or depth.max() > 1
                or not isinstance(sequence, int) or sequence < 0
                or not isinstance(timestamp_ns, int) or timestamp_ns < 0):
            raise ValueError('Expected bounded RGB, normalized float32 depth and frame identity')
        gray = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY), depth.shape[::-1], interpolation=cv2.INTER_AREA)
        reason = None
        if self.previous is None:
            reason = 'start'
        elif self.previous.shape != depth.shape or self.source_shape != frame.shape:
            reason = 'resize'
        elif sequence != self.sequence + 1:
            reason = 'sequence_gap'
        elif not 0 < timestamp_ns-self.timestamp <= 50_000_000:
            reason = 'timestamp_discontinuity'
        elif cut or np.abs(cv2.resize(gray, (32, 32)).astype(np.float32)
                            - cv2.resize(self.gray, (32, 32)).astype(np.float32)).mean()/255 > .18:
            reason = 'cut'
        if reason:
            result, accepted = depth.copy(), np.zeros(depth.shape, bool)
        else:
            forward = self.forward.calc(self.gray, gray, None)
            backward = self.backward.calc(gray, self.gray, None)
            result, accepted = align_history(depth, self.previous, gray, self.gray, forward, backward)
        age = 0 if reason else timestamp_ns-self.timestamp
        # Never feed the filtered output back; at most one previous raw frame contributes.
        self.previous, self.gray = depth.copy(), gray.copy()
        self.sequence, self.timestamp = sequence, timestamp_ns
        self.source_shape = frame.shape
        return result, dict(reset=reason, accepted_fraction=float(accepted.mean()),
                            maximum_history_age_ns=age, recursive_history=False)
