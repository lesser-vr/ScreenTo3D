"""Bounded cross-process BGRA mailbox. No Qt or capture imports."""

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
            self.error.value = str(message).encode("utf-8")[:1000]
            self.meta[STATE] = FAILED


def validate_shape(width, height):
    if not (16 <= width <= MAX_WIDTH and 16 <= height <= MAX_HEIGHT):
        raise ValueError(
            f"캡처 크기 {width}×{height}는 원본 미리보기 범위(최대 {MAX_WIDTH}×{MAX_HEIGHT}) 밖입니다."
        )
