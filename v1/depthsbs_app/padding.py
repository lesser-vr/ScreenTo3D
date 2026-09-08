"""Explicit experimental padding refinement; defaults remain disabled."""
from dataclasses import dataclass

import numpy as np

from depthsbs_app.stereo import refine_flat_background


@dataclass(frozen=True)
class PaddingPolicy:
    black_ceiling: int = 8
    max_edge_fraction: float = .10
    minimum_pixels: int = 2
    symmetry_pixels: int = 2
    transition_pixels: int = 2
    minimum_content: int = 32


@dataclass(frozen=True)
class ContentRegion:
    # Actual content bounds followed by inset bounds for refinement.
    x0: int
    y0: int
    x1: int
    y1: int
    ix0: int
    iy0: int
    ix1: int
    iy1: int


def detect_content(frame, policy=PaddingPolicy()):
    if not isinstance(frame, np.ndarray) or frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError('Padding detection requires uint8 RGB')
    h, w = frame.shape[:2]
    if min(h, w) < policy.minimum_content:
        return None
    dark = np.max(frame, axis=2) <= policy.black_ceiling
    def edges(flags):
        content = np.flatnonzero(~flags)
        return (int(content[0]), int(len(flags)-1-content[-1])) if content.size else (len(flags), len(flags))
    left, right = edges(dark.all(axis=0))
    top, bottom = edges(dark.all(axis=1))
    if not any((left, right, top, bottom)):
        return None
    for a, b, extent in ((left, right, w), (top, bottom, h)):
        if (a or b) and (min(a, b) < policy.minimum_pixels or max(a, b) > extent*policy.max_edge_fraction or
                        abs(a-b) > policy.symmetry_pixels):
            return None
    x0, y0, x1, y1 = left, top, w-right, h-bottom
    guard = policy.transition_pixels
    ix0, iy0 = x0+(guard if left else 0), y0+(guard if top else 0)
    ix1, iy1 = x1-(guard if right else 0), y1-(guard if bottom else 0)
    if min(ix1-ix0, iy1-iy0) < policy.minimum_content:
        return None
    return ContentRegion(x0, y0, x1, y1, ix0, iy0, ix1, iy1)


def padding_candidate(frame, depth, *, policy=PaddingPolicy(), **options):
    # Preserve the accepted behavior exactly for already-eligible scenes.
    baseline = refine_flat_background(frame, depth, **options)
    if baseline is not depth:
        return baseline, None
    region = detect_content(frame, policy)
    if region is None:
        return depth, None
    ys, xs = slice(region.iy0, region.iy1), slice(region.ix0, region.ix1)
    view = depth[ys, xs]
    refined = refine_flat_background(frame[ys, xs], view, **options)
    if refined is view:
        return depth, None
    result = depth.copy()
    result[ys, xs] = refined
    return result, region


def refine_padding_background(frame, depth, *, policy=PaddingPolicy(), **options):
    return padding_candidate(frame, depth, policy=policy, **options)[0]


def restore_padding(sbs, source, region):
    """Restore only confidently detected bar pixels, before lossy encoding."""
    h, w = source.shape[:2]
    if sbs.shape != (h, w*2, 3) or sbs.dtype != source.dtype:
        raise ValueError('Padding restoration requires matching SBS/source geometry')
    if region is None:
        return sbs
    result = sbs.copy()
    for offset in (0, w):
        eye = result[:, offset:offset+w]
        eye[:region.y0] = source[:region.y0]
        eye[region.y1:] = source[region.y1:]
        eye[:, :region.x0] = source[:, :region.x0]
        eye[:, region.x1:] = source[:, region.x1:]
    return result


class PaddingRefiner:
    """Bounded eligibility state; never keep a stale region over changed content."""
    def __init__(self, stable_frames=3):
        if type(stable_frames) is not int or not 1 <= stable_frames <= 30:
            raise ValueError('Padding confirmation must be 1..30 frames')
        self.stable_frames = stable_frames
        self.pending = self.active = None
        self.streak = 0
        self.applied = self.warmup = self.bypassed = self.restored = self.resets = 0

    def reset(self):
        self.pending = self.active = None
        self.streak = 0
        self.resets += 1

    def refine(self, frame, depth, **options):
        result, region = padding_candidate(frame, depth, **options)
        self.active = None
        if region is None:
            self.pending = None
            self.streak = 0
            self.bypassed += 1
            return result
        self.streak = min(self.stable_frames, self.streak+1) if region == self.pending else 1
        self.pending = region
        if self.streak < self.stable_frames:
            self.warmup += 1
            return depth
        self.active = region
        self.applied += 1
        return result

    def restore(self, stereo, frame):
        if self.active is not None:
            self.restored += 1
        return restore_padding(stereo, frame, self.active)

    def telemetry(self):
        return dict(enabled=True, experimental=True, required_stable_frames=self.stable_frames,
                    applied_frames=self.applied, warmup_frames=self.warmup, bypassed_frames=self.bypassed,
                    restored_frames=self.restored, scene_cut_resets=self.resets)
