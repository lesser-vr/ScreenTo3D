"""Host conversions performed while the caller owns the mailbox lock.

Input conversion returns owned RGB. Output conversion writes into the bounded
shared slot; the caller publishes metadata only after conversion completes.
Neither function retains a view of shared memory.
"""

import cv2
import numpy as np


def capture_rgb(pixels, width, height):
    source = np.frombuffer(pixels, np.uint8, width * height * 4).reshape(
        height, width, 4
    )
    return cv2.cvtColor(source, cv2.COLOR_BGRA2RGB)


def publish_rgb(pixels, frame):
    height, width, _ = frame.shape
    target = np.frombuffer(pixels, np.uint8, width * height * 4).reshape(
        height, width, 4
    )
    cv2.cvtColor(frame, cv2.COLOR_RGB2BGRA, dst=target)
