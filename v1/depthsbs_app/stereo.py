"""Visibility-aware CPU reference projection; no inverse-depth lookup."""
import numpy as np
import cv2


def guide_depth(frame, depth, radius=8, epsilon=0.0001):
    guide = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    def mean(value):
        return cv2.boxFilter(value, -1, (radius * 2 + 1, radius * 2 + 1), borderType=cv2.BORDER_REFLECT)
    mean_i, mean_p = mean(guide), mean(depth)
    covariance = mean(guide * depth) - mean_i * mean_p
    variance = mean(guide * guide) - mean_i * mean_i
    a = covariance / (np.maximum(variance, 0) + epsilon)
    b = mean_p - a * mean_i
    return np.clip(mean(a) * guide + mean(b), 0, 1)


def refine_flat_background(frame, depth, tolerance=0.04, minimum_coverage=0.35, radius=8):
    """Conservative border-connected uniform-backdrop refinement, any color.

    Not a semantic/person mask: bypass when the border or scene is not uniform.
    Preserve interior depth; only align the foreground rim and flat backdrop.
    """
    border = np.concatenate((frame[0], frame[-1], frame[:, 0], frame[:, -1]))
    color = np.median(border, axis=0)
    if np.mean(np.max(np.abs(border.astype(np.float32) - color), axis=1) <= tolerance * 255) < .98:
        return depth
    matches = np.max(np.abs(frame.astype(np.float32) - color), axis=2) <= tolerance * 255
    if not minimum_coverage <= np.mean(matches) <= .98:
        return depth
    _, labels = cv2.connectedComponents(matches.astype(np.uint8), connectivity=4)
    border_labels = np.unique(np.concatenate((labels[0], labels[-1], labels[:, 0], labels[:, -1])))
    background = np.isin(labels, border_labels[border_labels != 0])
    if np.mean(background) < minimum_coverage:
        return depth
    foreground = (~background).astype(np.uint8)
    _, components = cv2.connectedComponents(foreground, connectivity=4)
    counts = np.bincount(components.ravel())
    sums = np.bincount(components.ravel(), weights=depth.ravel())
    component_depth = (sums / np.maximum(counts, 1))[components].astype(np.float32)
    distance = cv2.distanceTransform(foreground, cv2.DIST_L2, 3)
    interior_weight = np.minimum(distance / max(1, radius * 4), 1)
    result = depth.copy()
    result[~background] = (component_depth * (1 - interior_weight) + depth * interior_weight)[~background]
    result[background] = np.median(depth[background])
    return result


def project_eye(frame, depth, shift):
    """Project source pixels, nearer depth wins; fill holes from farther side.

    Equal-depth collisions select the higher source index deterministically.
    Depth priority is quantized to 16 bits. Holes use the farther of the nearest
    visible left/right samples; unseen texture cannot be reconstructed exactly.
    """
    height, width = depth.shape
    source = np.arange(height * width, dtype=np.uint32).reshape(height, width)
    columns = np.arange(width, dtype=np.int32)[None, :]
    target_x = np.rint(columns + shift).astype(np.int32)
    valid = (target_x >= 0) & (target_x < width)
    target = (source // width) * width + np.clip(target_x, 0, width - 1)
    priority = ((np.clip(depth, 0, 1) * 65535).astype(np.uint64) + 1) << 32
    priority |= source.astype(np.uint64)
    winners = np.zeros(height * width, dtype=np.uint64)
    np.maximum.at(winners, target[valid], priority[valid])
    winners = winners.reshape(height, width)
    occupied = winners != 0
    owners = (winners & np.uint64(0xffffffff)).astype(np.int64)
    result = frame.reshape(-1, 3)[owners]
    if not occupied.all():
        rows = np.arange(height)[:, None]
        z = (winners >> 32).astype(np.float64)
        left = np.maximum.accumulate(np.where(occupied, columns, -1), axis=1)
        right = np.minimum.accumulate(np.where(occupied, columns, width)[:, ::-1], axis=1)[:, ::-1]
        left_valid, right_valid = left >= 0, right < width
        left = np.clip(left, 0, width - 1)
        right = np.clip(right, 0, width - 1)
        choose_left = left_valid & (~right_valid | (z[rows, left] <= z[rows, right]))
        fill_x = np.where(choose_left, left, right)
        holes = ~occupied
        result[holes] = result[rows, fill_x][holes]
        # Defensive fallback for an entirely projected-out row.
        empty = ~occupied.any(axis=1)
        result[empty] = frame[empty]
    return result
