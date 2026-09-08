"""Fixed-profile RGB preprocessing, checked against pinned VDA transform.

Implements cubic lower-bound resize + ImageNet normalization; only the accepted
allowlisted 518x896/518x924 profiles are supported. No upstream imports at runtime.
"""
import cv2
import numpy as np
from .vda_artifacts import validate_input


def preprocess(frame, shape=(518, 896)):
    if not isinstance(frame, np.ndarray) or frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError('VDA requires uint8 RGB [H,W,3]')
    validate_input({'width': frame.shape[1], 'height': frame.shape[0]}, shape)
    image = cv2.resize(frame.astype(np.float32) / 255.0, (shape[1], shape[0]), interpolation=cv2.INTER_CUBIC)
    # Float64 intermediates deliberately match the upstream Python-list
    # normalization followed by PrepareForNet's final float32 cast.
    normalized = (image - [.485, .456, .406]) / [.229, .224, .225]
    return np.ascontiguousarray(normalized.transpose(2, 0, 1)).astype(np.float32)
