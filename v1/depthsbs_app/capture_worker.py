"""Isolated Windows Graphics Capture process; single bounded CPU readback slot."""

import time
import multiprocessing as mp
import os
from .capture_mailbox import (
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
    RUNNING,
    STOPPED,
    FAILED,
    validate_shape,
)


def publish_pixels(mailbox, frame_buffer, width, height, *, retain_frame=False):
    """Publish one frame while the caller owns the mailbox lock.

    The normal path copies into fixed shared storage.  The opt-in retained-frame
    experiment instead transfers ownership of the mapped NumPy view to the
    single-slot mailbox; its native buffer exporter stays alive through the view.
    """
    if retain_frame:
        mailbox.pixels = frame_buffer
        return
    import numpy as np

    output = np.frombuffer(
        mailbox.pixels,
        dtype=np.uint8,
        count=width * height * 4,
    ).reshape(height, width, 4)
    np.copyto(output, frame_buffer)


def capture_worker(
    source,
    cursor,
    mailbox,
    *,
    minimum_update_interval=16,
    capture_telemetry=None,
    retain_frame=False,
):
    control = None
    recorder = None
    if capture_telemetry is not None:
        from .capture_telemetry import CaptureRecorder

        recorder = CaptureRecorder(capture_telemetry)
    try:
        if type(minimum_update_interval) is not int or minimum_update_interval not in (
            0,
            16,
        ):
            raise ValueError("Invalid capture update interval")
        if type(retain_frame) is not bool:
            raise ValueError("Invalid capture frame ownership mode")
        import numpy as np
        from windows_capture import WindowsCapture
        from .capture_sources import validate_source, enable_capture_dpi

        enable_capture_dpi()
        validate_source(source)
        kwargs = (
            {"window_hwnd": source["id"]}
            if source["kind"] == "window"
            else {"monitor_index": source["id"]}
        )
        capture = WindowsCapture(
            cursor_capture=cursor,
            draw_border=True,
            minimum_update_interval=minimum_update_interval,
            dirty_region=False,
            **kwargs,
        )
        sequence = 0
        contention = 0
        dimensions = None

        @capture.event
        def on_frame_arrived(frame, internal):
            nonlocal sequence, contention, dimensions
            callback_ns = time.perf_counter_ns()
            if mailbox.stop.is_set():
                internal.stop()
                return
            outcome = 2  # failed unless a successful publication/contention follows
            source_ns = 0
            try:
                validate_shape(frame.width, frame.height)
                if frame.frame_buffer.dtype != np.uint8 or frame.frame_buffer.shape != (
                    frame.height,
                    frame.width,
                    4,
                ):
                    raise ValueError(
                        "지원하지 않는 캡처 픽셀 형식입니다. SDR 원본 미리보기만 지원합니다."
                    )
                sequence += 1
                source_ns = int(frame.timespan) * 100
                if not mailbox.lock.acquire(False):
                    contention += 1
                    outcome = 1
                    return
                try:
                    m = mailbox.meta
                    if m[SEQ] > m[ACK]:
                        m[REPLACED] += 1
                    shape = (frame.width, frame.height)
                    if dimensions is not None and shape != dimensions:
                        m[RESIZES] += 1
                    dimensions = shape
                    publish_pixels(
                        mailbox,
                        frame.frame_buffer,
                        frame.width,
                        frame.height,
                        retain_frame=retain_frame,
                    )
                    m[WIDTH], m[HEIGHT] = shape
                    m[SEQ] = m[RECEIVED] = sequence
                    m[SOURCE_NS] = source_ns
                    m[CALLBACK_NS] = callback_ns
                    m[COPY_NS] = time.perf_counter_ns() - callback_ns
                    m[CONTENTION] = contention
                    m[STATE] = RUNNING
                    outcome = 0
                finally:
                    mailbox.lock.release()
            except Exception as error:
                mailbox.fail(error)
                internal.stop()
            finally:
                if recorder is not None:
                    recorder.observe(
                        callback_ns, time.perf_counter_ns(), source_ns, outcome
                    )

        @capture.event
        def on_closed():
            if not mailbox.stop.is_set():
                mailbox.fail(
                    "캡처 대상이 닫혔거나 접근이 중단되었습니다. 대상을 다시 선택하세요."
                )

        control = capture.start_free_threaded()
        while not mailbox.stop.wait(0.1):
            parent = mp.parent_process()
            if parent is not None and not parent.is_alive():
                # Capture-only process has no output files. Never keep recording
                # desktop pixels after an abrupt disappearance of its GUI owner.
                os._exit(0)
            if control.is_finished():
                break
        # A retained NativeMappedFrame can keep a D3D staging resource mapped.
        # Release it before asking the native capture session to drain/stop.
        if retain_frame:
            with mailbox.lock:
                mailbox.pixels = None
        control.stop()
        control = None
        if recorder is not None:
            recorder.finish()
        with mailbox.lock:
            mailbox.meta[RECEIVED] = sequence
            mailbox.meta[CONTENTION] = contention
            if mailbox.meta[STATE] != FAILED:
                mailbox.meta[STATE] = STOPPED
    except BaseException as error:
        mailbox.fail(error)
    finally:
        if control is not None:
            try:
                if retain_frame:
                    with mailbox.lock:
                        mailbox.pixels = None
                control.stop()
            except BaseException:
                pass
