"""Host conversions performed while the caller owns the mailbox lock.

Input conversion returns owned RGB. Output conversion writes into the bounded
shared slot; the caller publishes metadata only after conversion completes.
Conversions retain no borrowed view; capture_bgra is a lock-scoped borrowed view.
"""

import cv2
import numpy as np


def capture_bgra(pixels, width, height):
    """Borrow BGRA under the mailbox lock, preserving WGC row pitch."""
    if isinstance(pixels, np.ndarray) and pixels.ndim == 3:
        if pixels.dtype != np.uint8 or pixels.shape != (height, width, 4):
            raise ValueError("Invalid captured BGRA array")
        # Mapped D3D rows may include alignment padding. Flattening this view
        # with frombuffer rejects it (or would read padding as image pixels).
        return pixels
    return np.frombuffer(pixels, np.uint8, width * height * 4).reshape(
        height, width, 4
    )


def capture_rgb(pixels, width, height):
    source = capture_bgra(pixels, width, height)
    return cv2.cvtColor(source, cv2.COLOR_BGRA2RGB)


def publish_rgb(pixels, frame):
    height, width, _ = frame.shape
    target = np.frombuffer(pixels, np.uint8, width * height * 4).reshape(
        height, width, 4
    )
    cv2.cvtColor(frame, cv2.COLOR_RGB2BGRA, dst=target)
