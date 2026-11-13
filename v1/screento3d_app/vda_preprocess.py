"""Original VDA RGB transform on native ratios; edge-padded fit on other ratios."""
import cv2
import numpy as np
from .vda_artifacts import content_rect


def preprocess(frame, shape=(518, 896)):
    if not isinstance(frame, np.ndarray) or frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError('VDA requires uint8 RGB [H,W,3]')
    top, left, h, w = content_rect(frame.shape[1], frame.shape[0], shape)
    image = cv2.resize(frame.astype(np.float32) / 255.0, (w, h), interpolation=cv2.INTER_CUBIC)
    if (h, w) != tuple(shape):
        image = cv2.copyMakeBorder(image, top, shape[0]-h-top, left, shape[1]-w-left, cv2.BORDER_REPLICATE)
    # Float64 intermediates deliberately match the upstream Python-list
    # normalization followed by PrepareForNet's final float32 cast.
    normalized = (image - [.485, .456, .406]) / [.229, .224, .225]
    return np.ascontiguousarray(normalized.transpose(2, 0, 1)).astype(np.float32)
