"""Bounded cross-process BGRA mailbox. No Qt or capture imports."""

from .messages import Message as M
from .messages import encode_message

import ctypes
from dataclasses import dataclass

MAX_WIDTH, MAX_HEIGHT = 4096, 2160
MAX_BYTES = MAX_WIDTH * MAX_HEIGHT * 4
(
    SEQ,
    ACK,
    WIDTH,
    HEIGHT,
    RECEIVED,
    REPLACED,
    SOURCE_NS,
    CALLBACK_NS,
    COPY_NS,
    STATE,
    RESIZES,
    CONTENTION,
) = range(12)
STARTING, RUNNING, STOPPED, FAILED = range(4)


@dataclass
class Mailbox:
    pixels: object
    meta: object
    error: object
    lock: object
    stop: object

    @classmethod
    def create(cls, context, *, sbs=False, metadata_only=False):
        return cls(
            None
            if metadata_only
            else context.RawArray(ctypes.c_ubyte, MAX_BYTES * (2 if sbs else 1)),
            context.RawArray(ctypes.c_longlong, 12),
            context.RawArray(ctypes.c_char, 1024),
            context.Lock(),
            context.Event(),
        )

    def fail(self, message):
        with self.lock:
            self.error.value = encode_message(message)
            self.meta[STATE] = FAILED


def validate_shape(width, height):
    if not (16 <= width <= MAX_WIDTH and 16 <= height <= MAX_HEIGHT):
        raise ValueError(
            M('Capture size {v0}×{v1} exceeds the preview limit of {v2}×{v3}.', v0=width, v1=height, v2=MAX_WIDTH, v3=MAX_HEIGHT)
        )
