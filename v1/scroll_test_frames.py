"""Owned deterministic scrolling/text supplement, never claimed as web footage."""

import cv2
import numpy as np


class ScrollFrames:
    def __init__(self, count=60):
        self.count = count

    def __getitem__(self, index):
        if index < 0:
            index += self.count
        if not 0 <= index < self.count:
            raise IndexError(index)
        frame = np.full((720, 1280, 3), 24, np.uint8)
        for line in range(-1, 16):
            y = line * 56 - (index * 9) % 56
            cv2.putText(
                frame,
                f"ScreenTo3D 0123456789 / SCROLL {line}",
                (35, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (220, 225, 235),
                1,
                cv2.LINE_AA,
            )
        x = 150 + (index * 31) % 850
        cv2.rectangle(frame, (x, 180), (x + 110, 550), (60, 160, 220), -1)
        cv2.line(frame, (x + 119, 180), (x + 119, 550), (240, 230, 180), 1)
        if index >= 30:
            frame = 255 - frame
        return frame

    def __iter__(self):
        for index in range(self.count):
            yield self[index]
