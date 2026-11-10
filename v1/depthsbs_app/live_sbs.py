"""Owned, bounded model-defined TensorRT worker with explicit delivery.

Capture runs on a thread; CUDA objects remain on the worker's main thread.
Native delivery exports owned D3D resources through bounded descriptors only.
No frame is recorded and no CPU renderer fallback occurs.
"""

from .messages import Message as M
from .messages import decode_message, encode_message

import multiprocessing as mp
import os
import threading
import time
from contextlib import ExitStack
from dataclasses import replace
from .live_model import model_adapter

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
DEFAULT_STEREO_QUALITY = "detail"

PROCESSED, INPUT_REPLACED, RESETS, PREPROCESS_NS, DEPTH_NS, STEREO_NS, TOTAL_NS = range(
    7
)
H2D_BYTES, D2H_BYTES, SYNCS = range(7, 10)
BACKGROUND_NS = 19
INFERRED, REUSED = range(10, 12)
INPUT_COPY_NS, INPUT_COLOR_NS, OUTPUT_COLOR_NS, OUTPUT_COPY_NS = range(20, 24)
RESET_START, RESET_RESIZE, RESET_GAP, RESET_CUT = range(30, 34)
SBS_REUSED = 34
OVDA_RETAINED_GAPS, OVDA_CACHE_USED, OVDA_FULL_CONTEXT, OVDA_CACHE_SUM, OVDA_STREAK, OVDA_STREAK_MAX = range(35,41)
GPU_USAGE, GPU_USAGE_NS = range(41,43)
STAT_COUNT = 43
DEFAULT_CAPTURE_INTERVAL_MS = 0
MAX_HISTORY_GAP_NS = 100_000_000
VDA_SINGLE_SKIP_NS = 50_000_000
OVDA_SHORT_SKIP_NS = 50_000_000


def resolve_gpu_capture(source, model, gpu_path):
    default = '1' if model_adapter(model).gpu_capture and gpu_path and source['kind'] == 'window' else '0'
    value = os.environ.get('DEPTHSBS_GPU_CAPTURE', default)
    if value not in ('0', '1'):
        raise ValueError('DEPTHSBS_GPU_CAPTURE must be 0 or 1')
    return value == '1'


def resolve_history_policy(model, setting=None):
    """Live-only capabilities; file cadence and backend statefulness stay separate."""
    setting = os.environ.get('DEPTHSBS_DEPTH_HISTORY', 'continuous') if setting is None else setting
    if setting not in ('continuous', 'legacy', 'vda-single-skip'):
        raise ValueError('Invalid depth history diagnostic setting')
    adapter = model_adapter(model)
    return dict(
        allow_coalescing=setting != 'legacy' and adapter.coalesced_history,
        vda_single_skip=adapter.single_skip_history and setting in ('continuous', 'vda-single-skip'),
        ovda_short_skip=setting == 'continuous' and adapter.short_skip_history,
    )


def reset_reason(previous_sequence, sequence, previous_shape, shape, cut, *,
                 previous_source_ns=None, source_ns=None, allow_coalescing=False, vda_single_skip=False,
                 ovda_short_skip=False):
    if previous_sequence is None:
        return "start"
    if previous_shape != shape:
        return "resize"
    if ovda_short_skip:
        if cut:
            return 'cut'
        # One missing capture update at most. Cache positions count accepted
        # model updates, not absolute capture IDs; never insert fake frames.
        if (type(previous_sequence) is not int or type(sequence) is not int
                or not 1 <= sequence-previous_sequence <= 2
                or type(previous_source_ns) is not int or type(source_ns) is not int
                or previous_source_ns <= 0
                or not 0 < source_ns-previous_source_ns <= OVDA_SHORT_SKIP_NS):
            return 'gap'
        return None
    if allow_coalescing or vda_single_skip:
        # Latest-frame capture normally replaces frames while inference is busy.
        # Both history policies require a forward source clock and sequence.
        if (type(previous_sequence) is not int or type(sequence) is not int
                or sequence <= previous_sequence or type(previous_source_ns) is not int
                or type(source_ns) is not int or previous_source_ns <= 0
                or not 0 < source_ns - previous_source_ns <= MAX_HISTORY_GAP_NS):
            return "gap"
        if vda_single_skip and sequence != previous_sequence + 1:
            if sequence != previous_sequence + 2 or source_ns - previous_source_ns > VDA_SINGLE_SKIP_NS:
                return "gap"
        return "cut" if cut else None
    if sequence != previous_sequence + 1:
        return "gap"
    return "cut" if cut else None


def record_reset(stats, reason):
    """Count a completed reset without recording source identity or pixels.

    Total/breakdown reads are not atomic while processing. These are selected
    reset reasons, not independent counts of simultaneous events.
    """
    index = {"start": RESET_START, "resize": RESET_RESIZE,
             "gap": RESET_GAP, "cut": RESET_CUT}[reason]
    stats[index] += 1
    stats[RESETS] += 1
    stats[OVDA_STREAK] = 0


def record_ovda_inference(stats, cached):
    """Bounded metadata only: slots actually available BEFORE this inference."""
    if type(cached) is not int or not 0 <= cached <= 15:
        raise ValueError('Invalid oVDA cache occupancy')
    stats[OVDA_CACHE_USED] = cached
    stats[OVDA_CACHE_SUM] += cached
    stats[OVDA_FULL_CONTEXT] += int(cached == 15)
    stats[OVDA_STREAK] += 1
    stats[OVDA_STREAK_MAX] = max(stats[OVDA_STREAK_MAX], stats[OVDA_STREAK])


def validate_strength(value):
    if not 0.25 <= value <= 2.0:
        raise ValueError(M('Depth strength must be between 0.25 and 2.0.'))
    return float(value)


def resolve_renderer(model, gpu, strength=1.0, setting=None):
    setting = os.environ.get('DEPTHSBS_STEREO_RENDERER','cuda') if setting is None else setting
    if setting not in ('cuda','rowflow-sym'):
        raise ValueError('DEPTHSBS_STEREO_RENDERER must be cuda or rowflow-sym')
    if setting=='rowflow-sym' and (not model_adapter(model).rowflow or not gpu or not 0.25 <= strength <= 5/2.6):
        raise ValueError(M('The RowFlow trial requires the Balanced/Base GPU path and depth strength at most 1.92.'))
    return setting


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
    gpu_capture_snapshot=None,
    renderer_snapshot=None,
    preparation=None,
    vfg_enabled=False,
    output_hz=0,
    stereo_layout="full-sbs",
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
        from .live_policy import StaticSbsReuse, resolve_live, refresh_live, same_rgb
        from .live_host_bridge import capture_rgb, publish_rgb

        from dataclasses import replace
        from .stereo_layout import dimensions, pack
        dimensions(source["width"], source["height"], stereo_layout)
        policy = replace(resolve_live(mode, validate_strength(strength)), stereo_layout=stereo_layout)
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
        model = model_adapter(selected_model)
        policy = model.apply_live_policy(policy)
        history = resolve_history_policy(selected_model)
        vda_single_skip = history['vda_single_skip']
        ovda_short_skip = history['ovda_short_skip']
        coalesced_history = (history['allow_coalescing']
                             and not backend.spec.stateful and not backend.spec.requires_every_frame)
        stereo_quality = os.environ.get("DEPTHSBS_STEREO_QUALITY", DEFAULT_STEREO_QUALITY)
        if stereo_quality not in ("reference", "anchor", "subpixel", "stable", "coverage", "range", "motion", "window", "budget", "detail"):
            raise ValueError("Invalid stereo quality diagnostic setting")
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
        from .presentation_policy import PresentationCadence, WorkCadence
        requested_cadence = PresentationCadence(output_hz)
        work_cadence = WorkCadence(requested_cadence.hz) if native and not vfg_enabled else WorkCadence()
        renderer = resolve_renderer(selected_model,gpu_candidate,strength,renderer_snapshot)
        reuse = (StaticSbsReuse() if native and gpu_candidate and not vfg_enabled
                 and coalesced_history and selected_model in ('da2-small','da2-base')
                 and renderer == 'cuda' and stereo_quality == 'detail' else None)
        if renderer=='rowflow-sym':
            from .rowflow import bridge as rowflow_bridge, check
            compiler_bridge = rowflow_bridge()
            check(compiler_bridge,compiler_bridge.rowflow_protect_worker())
        use_gpu_capture = resolve_gpu_capture(source, selected_model, gpu_candidate) if gpu_capture_snapshot is None else gpu_capture_snapshot
        if type(use_gpu_capture) is not bool:
            raise ValueError('Invalid GPU capture snapshot')
        from .vfg_runtime import validate_selection
        validate_selection(vfg_enabled, selected_model, source['kind'], native,
                           use_gpu_capture and gpu_candidate, renderer)
        vfg_producer = None
        if vfg_enabled:
            from .vfg_delivery import TimedMailbox
            from .vfg_runtime import validate_runtime
            from .vfg_renderer import Producer, vfg_renderer
            if not isinstance(texture_mailbox, TimedMailbox):
                raise ValueError('VFG requires timed native delivery')
            validate_runtime()
            vfg_producer = Producer(texture_mailbox, output)
        if use_gpu_capture and (not model.gpu_capture or not gpu_candidate or not fused or capture_interval != '0'):
            raise ValueError('GPU capture requires a supported GPU output path and the default capture interval/bridge')
        if use_gpu_capture and capture_telemetry is not None:
            raise ValueError('Callback event recording is unavailable with GPU capture')
        backend = model.bind_capture(backend, use_gpu_capture)
        if native and (
            not gpu_candidate
            or type(session) is not int
            or session <= 0
            or output.pixels is not None
        ):
            raise ValueError("Invalid explicit native delivery snapshot")

        def wait_texture(predicate, cadence=None):
            deadline = time.monotonic() + 5
            while not predicate():
                parent = mp.parent_process()
                delay = cadence.wait_seconds(time.perf_counter_ns()) if cadence is not None else .001
                if output.stop.wait(delay) or (
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
            from .gpu_usage import UsageSampler
            gpu_usage = UsageSampler.current_cuda()
            scope.callback(gpu_usage.close)
            parent = mp.parent_process()
            if output.stop.is_set() or (parent is not None and not parent.is_alive()):
                return
            if use_gpu_capture:
                from .gpu_capture import GpuCapture
                from .gpu_frame import GpuFrame
                if engine.gpu_input is None:
                    raise ValueError('GPU capture requires GPU preprocessing')
                gpu_capture = scope.enter_context(GpuCapture(source, cursor, engine.device))
            else:
                capture = threading.Thread(
                    target=capture_worker,
                    args=(source, cursor, incoming),
                    kwargs={
                        "minimum_update_interval": int(capture_interval),
                        "capture_telemetry": capture_telemetry,
                        "retain_frame": True,
                    },
                    daemon=True,
                )
                capture.start()
            projection = synthesizer = None
            previous_sequence = previous_shape = None
            previous_source_ns = None
            inferred_frame = depth = None
            projection_scope = scope.enter_context(ExitStack())
            wait_seconds = 0.0 if fused else 0.001
            while not output.stop.wait(wait_seconds):
                sample = gpu_usage.poll(time.perf_counter_ns())
                if sample is not None:
                    stats[GPU_USAGE], stats[GPU_USAGE_NS] = sample
                parent = mp.parent_process()
                if parent is not None and not parent.is_alive():
                    break
                if work_cadence.period_ns:
                    # Wait BEFORE acquiring the latest input or running inference.
                    # Keep capacity for the new result; the other slot can still
                    # be displayed. Never wait for that displayed lease to vanish.
                    wait_texture(lambda: work_cadence.ready(time.perf_counter_ns()) and
                        (projection is None or bool(texture_mailbox.writable_slots(session,generation))),
                        cadence=work_cadence)
                if use_gpu_capture:
                    copy_start = time.perf_counter_ns()
                    captured = gpu_capture.read(engine.gpu_input.execution.stream)
                    if captured is None:
                        wait_seconds = .001
                        continue
                    wait_seconds = 0
                    bgra_device, meta = captured
                    stats[SYNCS] += 1  # Capture D3D/CUDA ownership completion.
                    width, height = meta['width'], meta['height']
                    m = [0] * 12
                    for key, name in ((WIDTH,'width'), (HEIGHT,'height'), (SEQ,'sequence'), (RECEIVED,'sequence'),
                            (SOURCE_NS,'source_ns'), (CALLBACK_NS,'callback_ns'), (REPLACED,'replaced'), (RESIZES,'resizes')):
                        m[key] = meta[name]
                    m[STATE] = RUNNING
                    m[COPY_NS] = time.perf_counter_ns() - copy_start
                    stats[INPUT_COPY_NS], stats[INPUT_COLOR_NS] = m[COPY_NS], 0
                    frame = GpuFrame(bgra_device, engine) if (width,height) == previous_shape else None
                else:
                    with incoming.lock:
                        m = list(incoming.meta)
                        if m[STATE] == FAILED:
                            raise RuntimeError(decode_message(bytes(incoming.error.value)))
                        if m[SEQ] <= m[ACK]:
                            if not capture.is_alive():
                                raise RuntimeError(M('The capture worker exited.'))
                            wait_seconds = .001
                            continue
                        wait_seconds = 0.0 if fused else .001
                        width, height = m[WIDTH], m[HEIGHT]
                        copy_start = time.perf_counter_ns()
                        if fused:
                            frame = capture_rgb(incoming.pixels, width, height)
                        else:
                            from .live_host_bridge import capture_bgra
                            bgra = capture_bgra(incoming.pixels, width, height).copy()
                        incoming.meta[ACK] = m[SEQ]
                        stats[INPUT_COPY_NS] = 0 if fused else time.perf_counter_ns() - copy_start
                        if fused:
                            stats[INPUT_COLOR_NS] = time.perf_counter_ns() - copy_start
                started = time.perf_counter_ns()
                work_cadence.emitted(started)
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
                    previous_sequence, m[SEQ], previous_shape, shape, cut,
                    previous_source_ns=previous_source_ns, source_ns=m[SOURCE_NS],
                    allow_coalescing=coalesced_history, vda_single_skip=vda_single_skip,
                    ovda_short_skip=ovda_short_skip,
                )
                if (ovda_short_skip and reason is None and m[SEQ] == previous_sequence+2):
                    stats[OVDA_RETAINED_GAPS] += 1
                if shape != previous_shape:
                    if (
                        previous_shape is not None
                        and backend.input_validator is not None
                    ):
                        backend.input_validator({"width": width, "height": height})
                    if native and projection is not None:
                        from .texture_mailbox import RETIRED

                        texture_mailbox.retire(session, generation)
                        wait_texture(lambda: texture_mailbox.state() == RETIRED)
                    projection_scope.close()
                    # The CUDA consumer borrows the engine's stream. Destroy it
                    # (and retire native leases) before replacing that owner.
                    if previous_shape is not None and backend.input_validator is not None:
                        engine_scope.close()
                        engine = engine_scope.enter_context(backend.engine_factory(None))
                    if use_gpu_capture:
                        frame = GpuFrame(bgra_device, engine)
                    if gpu_candidate:
                        if renderer=='rowflow-sym':
                            from .rowflow import RowFlowRenderer
                            if preparation is not None:
                                preparation.value = encode_message(M('Preparing stereo… Optimization may take time for a new screen size.'), limit=500)
                            projection = projection_scope.enter_context(RowFlowRenderer(
                                width,height,policy,engine,native=native,stop=output.stop))
                            if preparation is not None:preparation.value = b''
                            parent = mp.parent_process()
                            if output.stop.is_set() or (parent is not None and not parent.is_alive()):
                                raise InterruptedError('RowFlow preparation stopped')
                        else:
                            gpu_factory = (vfg_renderer(selected_model) if vfg_enabled else
                                           model.renderer_factory(native=native, gpu_capture=use_gpu_capture))
                            projection = projection_scope.enter_context(
                                gpu_factory(width, height, policy, engine)
                            )
                            if model.coalesced_history:
                                projection.configure_live_quality(stereo_quality)
                            if vfg_producer is not None:
                                vfg_producer.renderer = projection
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
                    record_reset(stats, reason)
                if gpu_candidate:
                    projection.source_ns = m[SOURCE_NS]
                else:
                    synthesizer.source_ns = m[SOURCE_NS]
                same = None
                if reuse is not None and projection.static_capable:
                    # The existing thumbnail can reject a change cheaply. Only
                    # full RGB equality can authorize holding the displayed SBS.
                    same = (reason is None and scene is not None
                            and np.array_equal(scene.thumbnail, projection.scene_history.previous)
                            and same_rgb(frame, inferred_frame))
                    if reuse.hold(same, m[SOURCE_NS]):
                        projection.hold_static(scene)
                        previous_sequence, previous_source_ns = m[SEQ], m[SOURCE_NS]
                        stats[SBS_REUSED] += 1
                        stats[INPUT_REPLACED] = m[REPLACED]
                        if use_gpu_capture:
                            stats[D2H_BYTES] += frame.readback_bytes
                            stats[SYNCS] += frame.readback_syncs
                        with output.lock:
                            output.meta[RECEIVED] = m[RECEIVED]
                        continue
                    projection.set_same_input(reuse.stationary)
                before = (
                    (projection.h2d, projection.d2h, projection.syncs)
                    if gpu_candidate
                    else None
                )
                prep_start = time.perf_counter_ns()
                refresh = refresh_live(
                    frame, inferred_frame, stats[PROCESSED], policy, cut, same
                )
                if refresh != "reuse":
                    cached = engine.used if selected_model == 'ovda-small-c16' else None
                    if gpu_candidate:
                        depth_start = time.perf_counter_ns()
                        depth = projection.infer(frame)
                    else:
                        tensor = backend.prepare(frame)
                        depth_start = time.perf_counter_ns()
                        depth = backend.infer(engine, tensor)
                    inferred_frame = frame
                    stats[INFERRED] += 1
                    if cached is not None:
                        record_ovda_inference(stats,cached)
                    if not gpu_candidate:
                        uploaded, downloaded = model.host_io_bytes(engine, frame, depth)
                        stats[H2D_BYTES] += uploaded
                        stats[D2H_BYTES] += downloaded
                        stats[SYNCS] += 1
                else:
                    depth_start = time.perf_counter_ns()
                    stats[REUSED] += 1
                stereo_start = time.perf_counter_ns()
                if native and getattr(projection, "requires_texture_slot", True):
                    # Most renderers write directly into a leased native slot.
                    # A deferred publisher may render into its own GPU buffer,
                    # but must acquire the real slot immediately before publishing.
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
                if reuse is not None and projection.static_capable:
                    reuse.after_render(projection, m[SOURCE_NS])
                if not native:
                    rgb_sbs = pack(rgb_sbs, stereo_layout)
                color_start = time.perf_counter_ns()
                if not fused and not native:
                    rendered = cv2.cvtColor(rgb_sbs, cv2.COLOR_RGB2BGRA)
                    stats[OUTPUT_COLOR_NS] = time.perf_counter_ns() - color_start
                previous_sequence, previous_shape = m[SEQ], shape
                previous_source_ns = m[SOURCE_NS]
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
                    stats[BACKGROUND_NS] = int(projection.last["background_ms"] * 1e6)
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

                    publish_texture = vfg_producer.publish if vfg_producer is not None else texture_mailbox.publish
                    publish_texture(
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
                    o[WIDTH], o[HEIGHT] = dimensions(width, height, stereo_layout)
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
