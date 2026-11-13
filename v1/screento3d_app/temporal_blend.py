"""Continuous approach to full depth refresh; motion masks still refresh exactly."""

import numpy as np


def blend_depth(current, previous, changed, alpha, threshold, transition):
    if not 0 < transition <= threshold:
        raise ValueError("Invalid temporal transition width")
    delta = np.abs(current - previous)
    start = np.float32(threshold - transition)
    ramp = np.clip((delta - start) / np.float32(transition), 0, 1)
    weight = np.float32(alpha) + np.float32(1.0 - alpha) * ramp
    blended = weight * current + (np.float32(1) - weight) * previous
    return np.where(changed | (delta >= np.float32(threshold)), current, blended)
