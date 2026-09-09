"""Owned, bounded model-defined TensorRT worker with explicit delivery.

Capture runs on a thread; CUDA objects remain on the worker's main thread.
Native delivery exports owned D3D resources through bounded descriptors only.
No frame is recorded and no CPU renderer fallback occurs.
"""

import multiprocessing as mp
import os
import threading
import time
from contextlib import ExitStack
from dataclasses import replace

from .capture_mailbox import (
    Mailbox,
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
    FAILED,
    RUNNING,
    STOPPED,
)

# Shared latest metrics, not an unbounded event/frame queue.
PROCESSED, INPUT_REPLACED, RESETS, PREPROCESS_NS, DEPTH_NS, STEREO_NS, TOTAL_NS = range(
    7
)
H2D_BYTES, D2H_BYTES, SYNCS = range(7, 10)
INFERRED, REUSED = range(10, 12)
INPUT_COPY_NS, INPUT_COLOR_NS, OUTPUT_COLOR_NS, OUTPUT_COPY_NS = range(20, 24)
STAT_COUNT = 30
DEFAULT_CAPTURE_INTERVAL_MS = 0


def reset_reason(previous_sequence, sequence, previous_shape, shape, cut):
    if previous_sequence is None:
        return "start"
    if previous_shape != shape:
        return "resize"
    if sequence != previous_sequence + 1:
        return "gap"
    return "cut" if cut else None


def validate_strength(value):
    if not 0.25 <= value <= 2.0:
        raise ValueError("입체감은 0.25–2.0 범위여야 합니다.")
    return float(value)


def sbs_worker(
    source,
    cursor,
    output,
    stats,
    strength,
    mode="balanced",
    gpu_candidate=None,
    texture_mailbox=None,
    session=0,
    *,
    capture_telemetry=None,
    backend_snapshot=None,
):
    from .capture_worker import capture_worker

    capture = None
    profiler = None
    # Capture and SBS run in the same owned worker process. WGC's NumPy view
    # carries the mapped-frame owner, so only metadata/coordination must be
    # shared with the GUI process; allocating a 4K BGRA RawArray here would be
    # unused after the retained-frame handoff below.
    incoming = Mailbox.create(mp.get_context("spawn"), metadata_only=True)
    incoming.stop = output.stop
    try:
        import cv2
        import numpy as np
        from .desktop_jobs import BUNDLE
        from .resources import configure_resource_root

        configure_resource_root(BUNDLE)
        from .trt_backend import DepthEngine
        from .pipeline import StereoSynthesizer, preprocess
        from .live_projection import LiveProjection as factory
        from .live_policy import resolve_live, refresh_live
        from .live_host_bridge import capture_rgb, publish_rgb

        policy = resolve_live(mode, validate_strength(strength))
        selected_model = "da2-small"
        if backend_snapshot is None:
            # Direct diagnostic callers retain their explicit legacy DA2 Small
            # behavior. The product controller always supplies a snapshot.
            from .depth_backend import resolve_backend

            backend = resolve_backend(selected_model, DepthEngine, preprocess)
        else:
            from .live_backend import binding as create_live_binding

            backend = create_live_binding(
                backend_snapshot,
                mode,
                {"width": source["width"], "height": source["height"]},
                DepthEngine,
                preprocess,
            )
            selected_model = backend.spec.model_id
        policy = replace(policy, depth_backend=selected_model)
        # Explicit diagnostic A/B switch, never an automatic fallback.
        bridge = os.environ.get("DEPTHSBS_LIVE_HOST_BRIDGE", "fused")
        if bridge not in ("legacy", "fused"):
            raise ValueError("Invalid host bridge setting")
        fused = bridge == "fused"
        capture_interval = os.environ.get(
            "DEPTHSBS_LIVE_CAPTURE_INTERVAL_MS", str(DEFAULT_CAPTURE_INTERVAL_MS)
        )
        if capture_interval not in ("0", "16"):
            raise ValueError("Invalid live capture interval")
        profile_path = os.environ.get("DEPTHSBS_LIVE_PROFILE")
        if profile_path:
            import cProfile

            profiler = cProfile.Profile()
            profiler.enable()
        if gpu_candidate is None:
            setting = os.environ.get("DEPTHSBS_LIVE_GPU_CANDIDATE", "0")
            if setting not in ("0", "1"):
                raise ValueError("Invalid explicit GPU candidate setting")
            gpu_candidate = setting == "1"
        if type(gpu_candidate) is not bool:
            raise ValueError("Invalid GPU path snapshot")
        native = texture_mailbox is not None
        if (
            selected_model
            not in (
                "da2-small",
                "vda-small",
                "ovda-small-c16",
            )
            and gpu_candidate
        ):
            raise ValueError(
                "The live GPU path does not support the selected depth model"
            )
        if native and (
            not gpu_candidate
            or selected_model not in ("da2-small", "vda-small", "ovda-small-c16")
            or type(session) is not int
            or session <= 0
            or output.pixels is not None
        ):
            raise ValueError("Invalid explicit native delivery snapshot")

        def wait_texture(predicate):
            deadline = time.monotonic() + 5
            while not predicate():
                parent = mp.parent_process()
                if output.stop.wait(0.001) or (
                    parent is not None and not parent.is_alive()
                ):
                    raise InterruptedError("Native delivery stopped")
                if time.monotonic() > deadline:
                    raise TimeoutError("Native texture consumer did not acknowledge")

        generation = 0
        with ExitStack() as scope:
            engine_scope = ExitStack()
            scope.callback(engine_scope.close)
            engine = engine_scope.enter_context(backend.engine_factory(None))
            parent = mp.parent_process()
            if output.stop.is_set() or (parent is not None and not parent.is_alive()):
                return
            capture = threading.Thread(
                target=capture_worker,
                args=(source, cursor, incoming),
                kwargs={
                    "minimum_update_interval": int(capture_interval),
                    "capture_telemetry": capture_telemetry,
                    # WGC's NumPy view retains its owned mapped frame. The
                    # single latest-frame mailbox holds that owner until RGB
                    # conversion completes, avoiding a 4-byte-per-pixel copy.
                    "retain_frame": True,
                },
                daemon=True,
            )
            capture.start()
            projection = synthesizer = None
            previous_sequence = previous_shape = None
            inferred_frame = depth = None
            projection_scope = scope.enter_context(ExitStack())
            wait_seconds = 0.0 if fused else 0.001
            while not output.stop.wait(wait_seconds):
                parent = mp.parent_process()
                if parent is not None and not parent.is_alive():
                    break
                with incoming.lock:
                    m = list(incoming.meta)
                    if m[STATE] == FAILED:
                        raise RuntimeError(
                            incoming.error.value.decode("utf-8", "replace")
                        )
                    if m[SEQ] <= m[ACK]:
                        if not capture.is_alive():
                            raise RuntimeError("캡처 작업자가 종료되었습니다.")
                        wait_seconds = 0.001
                        continue
                    wait_seconds = 0.0 if fused else 0.001
                    width, height = m[WIDTH], m[HEIGHT]
                    copy_start = time.perf_counter_ns()
                    if fused:
                        frame = capture_rgb(incoming.pixels, width, height)
                    else:
                        bgra = (
                            np.frombuffer(
                                incoming.pixels,
                                dtype=np.uint8,
                                count=width * height * 4,
                            )
                            .reshape(height, width, 4)
                            .copy()
                        )
                    incoming.meta[ACK] = m[SEQ]
                    stats[INPUT_COPY_NS] = (
                        0 if fused else time.perf_counter_ns() - copy_start
                    )
                    if fused:
                        stats[INPUT_COLOR_NS] = time.perf_counter_ns() - copy_start
                started = time.perf_counter_ns()
                if not fused:
                    frame = cv2.cvtColor(bgra, cv2.COLOR_BGRA2RGB)
                    stats[INPUT_COLOR_NS] = time.perf_counter_ns() - started
                shape = (width, height)
                scene = (
                    synthesizer.inspect_scene(frame)
                    if gpu_candidate
                    and synthesizer is not None
                    and shape == previous_shape
                    else None
                )
                cut = (
                    scene.cut
                    if scene is not None
                    else (
                        not gpu_candidate
                        and synthesizer is not None
                        and shape == previous_shape
                        and synthesizer.is_scene_cut(frame)
                    )
                )
                reason = reset_reason(
                    previous_sequence, m[SEQ], previous_shape, shape, cut
                )
                if shape != previous_shape:
                    if (
                        previous_shape is not None
                        and backend.input_validator is not None
                    ):
                        backend.input_validator({"width": width, "height": height})
                        engine_scope.close()
                        engine = engine_scope.enter_context(
                            backend.engine_factory(None)
                        )
                    if native and projection is not None:
                        from .texture_mailbox import RETIRED

                        texture_mailbox.retire(session, generation)
                        wait_texture(lambda: texture_mailbox.state() == RETIRED)
                    projection_scope.close()
                    if gpu_candidate:
                        if selected_model in ("vda-small", "ovda-small-c16"):
                            from .live_source_gpu_candidate import (
                                LiveSourceGpuCandidate as gpu_factory,
                            )
                        else:
                            from .live_gpu_candidate import LiveGpuCandidate

                            gpu_factory = LiveGpuCandidate
                        if native:
                            if selected_model in ("vda-small", "ovda-small-c16"):
                                from .live_source_gpu_texture import (
                                    LiveSourceGpuTexture as gpu_factory,
                                )
                            else:
                                from .live_gpu_texture import (
                                    LiveGpuTexture as gpu_factory,
                                )

                        projection = projection_scope.enter_context(
                            gpu_factory(width, height, policy, engine)
                        )
                        if native:
                            from .texture_mailbox import INSTALLED

                            generation += 1
                            texture_mailbox.offer(
                                projection.pool.descriptor(session, generation),
                                session=session,
                                owned_pid=os.getpid(),
                            )
                            wait_texture(lambda: texture_mailbox.state() == INSTALLED)
                    else:
                        projection = projection_scope.enter_context(
                            factory(width, height)
                        )
                if reason:
                    scene = None  # Reset invalidates observations from the old history.
                    inferred_frame = depth = None
                    backend.reset(
                        engine,
                        {
                            "start": "start",
                            "resize": "source_change",
                            "gap": "discontinuity",
                            "cut": "scene_cut",
                        }[reason],
                    )
                    if gpu_candidate:
                        synthesizer = projection
                        synthesizer.reset()
                    else:
                        synthesizer = StereoSynthesizer(
                            width,
                            height,
                            policy,
                            projection,
                            paired_projection=projection.project_pair,
                        )
                    stats[RESETS] += 1
                before = (
                    (projection.h2d, projection.d2h, projection.syncs)
                    if gpu_candidate
                    else None
                )
                prep_start = time.perf_counter_ns()
                refresh = refresh_live(
                    frame, inferred_frame, stats[PROCESSED], policy, cut
                )
                if refresh != "reuse":
                    if gpu_candidate:
                        depth_start = time.perf_counter_ns()
                        depth = projection.infer(frame)
                    else:
                        tensor = backend.prepare(frame)
                        depth_start = time.perf_counter_ns()
                        depth = backend.infer(engine, tensor)
                    inferred_frame = frame
                    stats[INFERRED] += 1
                    if not gpu_candidate:
                        if selected_model == "da2-small":
                            stats[H2D_BYTES] += engine.input_bytes
                            stats[D2H_BYTES] += engine.output_bytes
                        else:
                            input_shape = getattr(
                                engine,
                                "input_shape",
                                (1, 3, *getattr(engine, "shape", frame.shape[:2])),
                            )
                            stats[H2D_BYTES] += int(np.prod(input_shape) * 4)
                            stats[D2H_BYTES] += depth.nbytes
                        stats[SYNCS] += 1
                else:
                    depth_start = time.perf_counter_ns()
                    stats[REUSED] += 1
                stereo_start = time.perf_counter_ns()
                if native:
                    wait_texture(
                        lambda: bool(
                            texture_mailbox.writable_slots(session, generation)
                        )
                    )
                    projection.slot = texture_mailbox.writable_slots(
                        session, generation
                    )[0]
                rgb_sbs = (
                    synthesizer.render(frame, depth, scene=scene)
                    if gpu_candidate
                    else synthesizer.render(frame, depth)
                )
                color_start = time.perf_counter_ns()
                if not fused and not native:
                    rendered = cv2.cvtColor(rgb_sbs, cv2.COLOR_RGB2BGRA)
                    stats[OUTPUT_COLOR_NS] = time.perf_counter_ns() - color_start
                previous_sequence, previous_shape = m[SEQ], shape
                stats[PROCESSED] += 1
                stats[INPUT_REPLACED] = m[REPLACED]
                stats[PREPROCESS_NS] = depth_start - prep_start
                stats[DEPTH_NS] = stereo_start - depth_start
                stats[STEREO_NS] = color_start - stereo_start
                if gpu_candidate:
                    for key, value, old in zip(
                        (H2D_BYTES, D2H_BYTES, SYNCS),
                        (projection.h2d, projection.d2h, projection.syncs),
                        before,
                    ):
                        stats[key] += value - old
                    # Stream intervals; stage 6 includes host background wait and is
                    # excluded in favor of separately measured CPU background work.
                    for key, value in zip(
                        range(12, 19), projection.gpu_ms[[0, 1, 2, 3, 4, 5, 7]]
                    ):
                        stats[key] = int(float(value) * 1e6)
                    stats[19] = int(projection.last["background_ms"] * 1e6)
                    stats[INPUT_COLOR_NS] += int(
                        projection.last.get("input_stage_ms", 0) * 1e6
                    )
                    for key, value in zip(range(24, 30), projection.projection_ms):
                        stats[key] = int(float(value) * 1e6)
                else:
                    stats[H2D_BYTES] += width * height * 11
                    stats[D2H_BYTES] += width * height * 6
                    stats[SYNCS] += 1
                if output.stop.is_set():
                    break
                if native:
                    from .texture_mailbox import TextureFrame

                    texture_mailbox.publish(
                        TextureFrame(
                            session,
                            generation,
                            rgb_sbs,
                            stats[PROCESSED],
                            m[SOURCE_NS],
                            m[CALLBACK_NS],
                        )
                    )
                with output.lock:
                    publish_start = time.perf_counter_ns()
                    o = output.meta
                    if o[SEQ] > o[ACK]:
                        o[REPLACED] += 1
                    if native:
                        stats[OUTPUT_COLOR_NS] = stats[OUTPUT_COPY_NS] = 0
                    elif fused:
                        publish_rgb(output.pixels, rgb_sbs)
                        stats[OUTPUT_COLOR_NS] = time.perf_counter_ns() - publish_start
                    else:
                        target = np.frombuffer(
                            output.pixels, dtype=np.uint8, count=rendered.size
                        ).reshape(rendered.shape)
                        np.copyto(target, rendered)
                    o[WIDTH], o[HEIGHT] = width * 2, height
                    o[SEQ] = stats[PROCESSED]
                    for key in (
                        RECEIVED,
                        SOURCE_NS,
                        CALLBACK_NS,
                        COPY_NS,
                        RESIZES,
                        CONTENTION,
                    ):
                        o[key] = m[key]
                    o[STATE] = RUNNING
                    stats[OUTPUT_COPY_NS] = (
                        0 if fused or native else time.perf_counter_ns() - publish_start
                    )
                    # Both bridge variants include input ownership through output
                    # publication. Wait-for-source/capture/Qt remain separate.
                    stats[TOTAL_NS] = time.perf_counter_ns() - copy_start
    except InterruptedError as error:
        if not output.stop.is_set():
            output.fail(error)
    except BaseException as error:
        output.fail(error)
    finally:
        output.stop.set()
        if capture is not None:
            capture.join(timeout=2)
        with output.lock:
            if output.meta[STATE] != FAILED:
                output.meta[STATE] = STOPPED
        if profiler is not None:
            profiler.disable()
            profiler.dump_stats(profile_path)
