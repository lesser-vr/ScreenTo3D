"""Bounded CPU diagnostic only: source-flow aligned normalized depth changes."""
import cv2
import numpy as np


def aligned_change(old_rgb, rgb, old_depth, depth, backward=None, forward=None):
    """Current-grid backward warp; consistency/photometric masks exclude ambiguity.

    RGB must be matching uint8, depths matching finite float32 in normalized units.
    Flow injection exists for analytic tests. No ground-truth or ghosting claim.
    """
    h, w = rgb.shape[:2]
    if (rgb.dtype != np.uint8 or old_rgb.dtype != np.uint8
            or rgb.shape != old_rgb.shape or rgb.shape != (h, w, 3)
            or depth.shape != (h, w) or old_depth.shape != (h, w)
            or not np.isfinite(depth).all() or not np.isfinite(old_depth).all()):
        raise ValueError('Invalid diagnostic RGB/depth pair')
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    old_gray = cv2.cvtColor(old_rgb, cv2.COLOR_RGB2GRAY)
    if backward is None:
        backward = cv2.calcOpticalFlowFarneback(gray, old_gray, None, .5, 3, 21, 3, 5, 1.2, 0)
    if forward is None:
        forward = cv2.calcOpticalFlowFarneback(old_gray, gray, None, .5, 3, 21, 3, 5, 1.2, 0)
    for flow in (backward, forward):
        if flow.shape != (h, w, 2) or not np.isfinite(flow).all():
            raise ValueError('Invalid flow')
    y, x = np.mgrid[:h, :w].astype(np.float32)
    mx, my = x + backward[..., 0], y + backward[..., 1]
    def warp(value):
        return cv2.remap(value.astype(np.float32), mx, my, cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_CONSTANT)
    valid = (mx >= 1) & (mx < w-2) & (my >= 1) & (my < h-2)
    valid &= np.linalg.norm(backward + warp(forward), axis=2) <= 1.0
    valid &= np.max(np.abs(rgb.astype(np.float32)-warp(old_rgb)), axis=2) <= 12
    valid = cv2.erode(valid.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    edges = cv2.dilate(cv2.Canny(gray, 60, 120), np.ones((5, 5), np.uint8)) != 0
    delta = np.abs(depth-warp(old_depth))
    def mean(mask):
        return float(delta[mask].mean()) if mask.any() else None
    return dict(valid_fraction=float(valid.mean()), edge_valid_fraction=float((valid & edges).mean()),
                aligned_mae=mean(valid), edge_aligned_mae=mean(valid & edges),
                unaligned_mae=float(np.abs(depth-old_depth)[valid].mean()) if valid.any() else None,
                median_motion_pixels=float(np.median(np.linalg.norm(backward[valid], axis=1))) if valid.any() else None)


class TemporalProbe:
    """Keeps one previous reduced RGB/depth pair and at most 124 scalar rows."""
    def __init__(self):
        self.previous = None
        self.rows = []

    def add(self, frame, raw_depth, *, cut=False):
        if len(self.rows) >= 124:
            raise ValueError('Diagnostic frame budget exceeded')
        h, w = frame.shape[:2]
        size = (min(480, w), max(16, round(h*min(480, w)/w)))
        rgb = cv2.resize(frame, size, interpolation=cv2.INTER_AREA)
        raw = np.asarray(raw_depth, dtype=np.float32).squeeze()
        if raw.ndim != 2 or not np.isfinite(raw).all():
            raise ValueError('Invalid diagnostic depth')
        low, high = np.percentile(raw, [5, 95])
        depth = cv2.resize(np.clip((raw-low)/max(high-low, 1e-6), 0, 1).astype(np.float32), size)
        row = dict(frame=len(self.rows), cut=bool(cut), excluded_reason=None)
        if cut:
            row['excluded_reason'] = 'scene_cut'
        elif self.previous is None:
            row['excluded_reason'] = 'first_frame'
        else:
            row.update(aligned_change(self.previous[0], rgb, self.previous[1], depth))
        self.previous = (rgb.copy(), depth.copy())
        self.rows.append(row)

    def report(self):
        keys = ('aligned_mae', 'edge_aligned_mae', 'unaligned_mae', 'valid_fraction', 'edge_valid_fraction')
        summary = {}
        for key in keys:
            values = [r[key] for r in self.rows if r.get(key) is not None]
            summary[key] = float(np.mean(values)) if values else None
        return dict(rows=self.rows, summary=summary,
                    note='480px-wide source Farneback flow; FB <=1px, RGB residual <=12/255, erode3; '
                         '5/95 per-frame raw-depth normalization, pre-EMA; cut pairs excluded. '
                         'No ground truth; normalization hides global scale drift; flow masks can exclude hardest edges. '
                         'Frame-average proxy, not a ghosting, spatial accuracy or comfort score.')
