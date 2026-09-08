"""Exact live cut predicate with compact history and single-use observations."""

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True, eq=False)
class SceneObservation:
    owner: object
    epoch: int
    frame: object
    thumbnail: object
    cut: bool


class LiveSceneHistory:
    def __init__(self, threshold):
        self.threshold = threshold
        self.previous = None
        self.epoch = 0

    def reset(self):
        self.previous = None
        self.epoch += 1

    def inspect(self, frame):
        if frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError("Invalid scene RGB frame")
        current = cv2.resize(frame, (32, 32)).astype(np.float32)
        cut = (
            self.previous is not None
            and float(np.mean(np.abs(current - self.previous))) / 255 > self.threshold
        )
        current.flags.writeable = False
        return SceneObservation(self, self.epoch, frame, current, bool(cut))

    def validate(self, observation, frame):
        if (
            not isinstance(observation, SceneObservation)
            or observation.owner is not self
            or observation.epoch != self.epoch
            or observation.frame is not frame
        ):
            raise ValueError("Expired or foreign scene observation")

    def commit(self, observation):
        self.validate(observation, observation.frame)
        # Thumbnail owns its pixels; do not retain the full input frame here.
        self.previous = observation.thumbnail
        self.epoch += 1
