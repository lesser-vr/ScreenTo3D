"""Both paths return QImage-owned storage; no mailbox view survives the call."""

import numpy as np
from PySide6.QtGui import QImage


class PreviewCopyPool:
    """Two owned slots; QImage detaches before writing if a reader still shares it."""

    def __init__(self):
        self.clear()

    def clear(self):
        self.images = []
        self.shape = None
        self.index = 0

    def copy(self, pixels, width, height):
        if not (16 <= width <= 8192 and 16 <= height <= 2160):
            raise ValueError("Invalid preview dimensions")
        if self.shape != (width, height):
            self.images = [QImage(width, height, QImage.Format_RGB32) for _ in range(2)]
            self.shape = (width, height)
            self.index = 0
        owned = self.images[self.index]
        self.index = (self.index + 1) % 2
        if owned.isNull() or owned.bytesPerLine() != width * 4:
            raise RuntimeError("Could not allocate owned preview image")
        target = np.frombuffer(owned.bits(), np.uint8, width * height * 4)
        np.copyto(target, np.frombuffer(pixels, np.uint8, width * height * 4))
        # A distinct handle ensures retained Python and Qt readers are immutable
        # across slot reuse; bits() performs copy-on-write for shared storage.
        return QImage(owned)


def copy_image(pixels, width, height, mode="qt"):
    if mode == "qt":
        return QImage(pixels, width, height, width * 4, QImage.Format_RGB32).copy()
    if mode != "numpy":
        raise ValueError("Invalid Qt image copy mode")
    result = QImage(width, height, QImage.Format_RGB32)
    if result.isNull() or result.bytesPerLine() != width * 4:
        raise RuntimeError("Could not allocate owned preview image")
    target = np.frombuffer(result.bits(), np.uint8, width * height * 4)
    source = np.frombuffer(pixels, np.uint8, width * height * 4)
    np.copyto(target, source)
    return result
