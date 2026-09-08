"""Fixed-size deterministic quality fixtures; no external media required."""
import numpy as np


def motion_frame(index, width=640, height=360):
    y, x = np.indices((height, width))
    cut = index >= 25
    checker = ((x // 12 + y // 12) % 2) * 35 + (195 if cut else 20)
    frame = np.repeat(checker[:, :, None], 3, axis=2).astype(np.uint8)
    depth = np.full((height, width), .1, np.float32)
    left = 20 + (index * 23) % (width - 100)
    mask = (x >= left) & (x < left + 70) & (y >= height // 3) & (y < height * 2 // 3)
    # Thin fingers joined to a larger moving body.
    mask |= (x >= left + 12) & (x < left + 16) & (y >= height // 4) & (y < height // 3)
    frame[mask] = (250, 35, 40)
    depth[mask] = .9
    return frame, depth
