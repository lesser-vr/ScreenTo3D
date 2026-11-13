"""Shared native VFG output for Small/Base; experiment launchers only."""
import ctypes as ct
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import threading
import time
from unittest.mock import patch

from screento3d_app.desktop_jobs import ROOT
from screento3d_app.live_source_gpu_candidate import LiveSourceGpuCandidate
from screento3d_app.live_texture_pool import LiveTexturePool
from screento3d_app.native_delivery import NativeDelivery
from screento3d_app.texture_mailbox import TextureMailbox, TextureFrame, RETIRING
from run_probe import PINS, SDK
from timing import Timeline

BRIDGE = ROOT / "out/vfg-native-bridge-detail/vfg_native_bridge.dll"
BRIDGE_HASH = "a5f0df818fae26fb8ecd3403cb6965d9cd034f1338121375d10a7461ce0b1671"
LAYOUT_HASH = "0394a7b790c92db37aaa49190e213edc65914e79625f03d38d62cf3c2911da85"
SMALL_LAYOUT_HASH = "d8cbabe89c36a7c3b224f8eb07cb3f458c92fb4e04280c55530f4b8d2db12849"
CTX = None


class TimedMailbox(TextureMailbox):
    @classmethod
    def create(cls, context):
        base = super().create(context)
        base.timing = context.RawArray(ct.c_longlong, 16)  # 8 words per existing slot.
        return base

    def publish_timed(self, frame, due, oldest, kind, base_id, ready):
        # WGC's compositor timestamp can lead CPU completion on fast paths.
        # Preserve both clocks; only the scheduled output must follow both.
        # Bound that lead so malformed timestamps cannot retain a slot forever.
        if (kind not in (0,1) or not 0 < oldest <= frame.source_ns <= due
                or not 0 < ready <= due or frame.source_ns - ready > 100_000_000):
            raise ValueError(f"Invalid VFG timing: source-to-ready={ready-frame.source_ns}ns, callback-to-ready={ready-frame.callback_ns}ns, ready-to-due={due-ready}ns, kind={kind}")
        if frame.slot not in self.writable_slots(frame.session, frame.generation):
            raise ValueError("VFG output slot is still leased")
        self._acquire()
        try:
            offset = frame.slot * 8
            self.timing[offset:offset+8] = [frame.sequence, due, frame.source_ns, oldest,
                                           kind, base_id, ready, frame.callback_ns]
        finally:
            self.lock.release()
        super().publish(frame)

    def frame_timing(self, frame):
        self._acquire()
        try:
            record = tuple(self.timing[frame.slot*8:frame.slot*8+8])
            if record[0] != frame.sequence:
                raise RuntimeError("Stale VFG timing descriptor")
            return record
        finally:
            self.lock.release()

    def publish(self, frame):
        if CTX is None:
            now = time.perf_counter_ns()
            return self.publish_timed(frame, max(now, frame.source_ns), frame.source_ns, 0, frame.sequence, now)
        return CTX.publish(frame)


class BridgePool(LiveTexturePool):
    library_path = BRIDGE
    library_sha256 = BRIDGE_HASH


class VfgOutputMixin:
    requires_texture_slot = False  # _project writes only its owned linear RGBA buffer.

    def __init__(self, width, height, policy, engine, *, diagnostic=False):
        self.pool = self.vfg = self.current = self.previous = self.middle = None
        self.current_window = self.previous_window = None
        self.dll_dirs = []
        self.valid = False
        self.timeline = Timeline()
        self.slot = 0
        if self.library_sha256 != self.expected_layout or policy.depth_backend != self.expected_model:
            raise ValueError("VFG experiment requires its model's pinned renderer layout")
        super().__init__(width, height, policy, engine)
        try:
            for relative, expected in PINS.items():
                if hashlib.sha256((SDK / relative).read_bytes()).hexdigest() != expected:
                    raise ValueError("VFG SDK integrity mismatch")
            if hashlib.sha256(BRIDGE.read_bytes()).hexdigest() != BRIDGE_HASH:
                raise ValueError("VFG bridge integrity mismatch")
            for folder in (SDK / "bin", SDK / "features/nvvfxvideoframegeneration/bin"):
                self.dll_dirs.append(os.add_dll_directory(str(folder)))
            os.environ["NV_VIDEO_EFFECTS_PATH"] = str(SDK / "bin")
            self.bridge = ct.CDLL(str(BRIDGE))
            self.bridge.live_texture_error.restype = ct.c_char_p
            self.bridge.vfg_create.argtypes = [ct.c_int, ct.c_int, ct.c_void_p]
            self.bridge.vfg_create.restype = ct.c_void_p
            self.bridge.vfg_destroy.argtypes = [ct.c_void_p]
            self.bridge.vfg_run.argtypes = [ct.c_void_p] * 4
            self.bridge.vfg_window_capture.argtypes = [ct.c_void_p] * 2
            self.bridge.vfg_window_apply.argtypes = [ct.c_void_p] * 4
            self.bridge.vfg_project.argtypes = [ct.c_void_p] * 2 + [ct.c_float] * 2 + [ct.c_int, ct.c_void_p]
            self.bridge.vfg_publish.argtypes = [ct.c_void_p] * 2 + [ct.c_int] * 3 + [ct.c_void_p]
            self.pool = BridgePool(width, height, diagnostic=diagnostic)
            torch = engine.torch
            self.execution_stream = getattr(engine, 'torch_stream', None)
            if self.execution_stream is None:
                self.execution_stream = engine.stream
            if self.execution_stream.cuda_stream != self._stream(engine):
                raise ValueError('VFG allocation stream differs from the model stream')
            with torch.cuda.stream(self.execution_stream):
                self.current, self.previous, self.middle = [torch.empty((height, width*2, 4), dtype=torch.uint8,
                    device=f"cuda:{engine.device}") for _ in range(3)]
                self.current_window, self.previous_window = [torch.zeros(2,dtype=torch.float32,
                    device=f"cuda:{engine.device}") for _ in range(2)]
            self.vfg = self.bridge.vfg_create(width * 2, height, self._stream(engine))
            self.check(self.vfg)
            if CTX is not None:
                CTX.renderer = self
                CTX.created += 1
        except BaseException:
            self.close()
            raise

    def check(self, value):
        if not value:
            raise RuntimeError(self.bridge.live_texture_error().decode("utf-8", "replace"))

    def reset(self):
        super().reset()
        # The worker now keeps ordinary coalescing separate from discontinuities.
        # Every actual reset invalidates both depth history and interpolation.
        self.valid = False

    def _project(self, frame, refined):
        try:
            self.check(self.bridge.vfg_project(self.handle, self.current.data_ptr(), self.stereo_convergence,
                max(1.0, self.width*self.policy.divergence), int(self.policy.conservative_stereo_coverage),
                refined.ctypes.data if refined is not None else None))
            if self.stereo_quality in ('window','budget','detail'):
                self.check(self.bridge.vfg_window_capture(self.handle,self.current_window.data_ptr()))
            self.d2h += 4
            self.syncs += 2
            return self.slot
        except BaseException:
            self.failed = True
            raise

    def _pack_result(self, projected):
        return projected

    def generate(self,previous,current,output,previous_window=None,current_window=None):
        self.check(self.bridge.vfg_run(self.vfg,previous.data_ptr(),current.data_ptr(),output.data_ptr()))
        if self.stereo_quality in ('window','budget','detail'):
            if previous_window is None:previous_window=self.previous_window
            if current_window is None:current_window=self.current_window
            self.check(self.bridge.vfg_window_apply(self.vfg,output.data_ptr(),
                previous_window.data_ptr(),current_window.data_ptr()))
            self.syncs += 1  # Generated-window repair completes before its ready timestamp.

    def publish_pixels(self, pixels, slot):
        self.pool.owner()
        self.check(self.bridge.vfg_publish(self.pool.handle, pixels.data_ptr(), self.width*2,
                                          self.height, slot, self._stream(self.engine)))

    def close(self):
        if hasattr(self, "thread") and self.thread != threading.get_ident():
            raise RuntimeError("Foreign VFG renderer owner")
        errors = []
        if self.vfg:
            try:
                self.check(self.bridge.vfg_destroy(self.vfg))
                if CTX is not None:
                    CTX.closed += 1
            except Exception as error:
                errors.append(error)
            self.vfg = None
        if self.pool:
            try:
                self.pool.close()
            except Exception as error:
                errors.append(error)
            self.pool = None
        try:
            super().close()
        except Exception as error:
            errors.append(error)
        self.current = self.previous = self.middle = None
        self.current_window = self.previous_window = None
        for directory in reversed(self.dll_dirs):
            directory.close()
        self.dll_dirs.clear()
        if errors:
            raise errors[0]


class VfgRenderer(VfgOutputMixin, LiveSourceGpuCandidate):
    expected_model = 'da2-base'
    expected_layout = LAYOUT_HASH


SUPPORTED_MODELS = ('da2-base', 'da2-small')


def vfg_renderer(model):
    if model == 'da2-base':
        return VfgRenderer
    if model == 'da2-small':
        # Small's input module imports TensorRT. Keep it out of the GUI process
        # until the selected worker actually creates a renderer.
        from small_native import SmallVfgRenderer
        return SmallVfgRenderer
    raise ValueError('Unsupported VFG depth model')


from screento3d_app.environment import get as app_env, required as app_env_required

class Producer:
    def __init__(self, mailbox, output):
        self.mailbox, self.output = mailbox, output
        self.renderer = None
        self.sequence = self.created = self.closed = 0
        self.generated = self.original = self.resets = 0
        self.last_reset = None
        self.vfg_ms = []
        self.publish_ms = []
        self.reset_counts = {}
        self.cut_bases = []

    def wait_slot(self, frame):
        deadline = time.monotonic() + 5
        while True:
            if self.output.stop.is_set():
                raise InterruptedError("VFG publication stopped")
            slots = self.mailbox.writable_slots(frame.session, frame.generation)
            if slots:
                return slots[0]
            if time.monotonic() > deadline:
                raise TimeoutError("VFG consumer stopped returning slots")
            self.output.stop.wait(0.001)

    def publish(self, frame):
        r = self.renderer
        began = time.perf_counter_ns()
        test_cut = int(app_env("SCREENTO3D_VFG_TEST_CUT_EVERY", "0"))
        if test_cut and frame.sequence % test_cut == 0:
            r.valid = False
        if not r.valid and len(self.cut_bases) < 10000:
            self.cut_bases.append(frame.sequence)
        interval = frame.source_ns - r.timeline.previous_source if r.timeline.previous_source else 0
        generate = r.valid and 0 < interval <= 100_000_000
        if generate:
            start = time.perf_counter_ns()
            r.generate(r.previous,r.current,r.middle)
            if len(self.vfg_ms) < 10000:
                self.vfg_ms.append((time.perf_counter_ns()-start)/1e6)
        ready = time.perf_counter_ns()
        plan = r.timeline.plan(frame.source_ns, ready, not generate)
        for kind, due, source, oldest in plan:
            slot = self.wait_slot(frame)
            r.publish_pixels(r.middle if kind else r.current, slot)
            self.sequence += 1
            emitted = TextureFrame(frame.session, frame.generation, slot, self.sequence, source, frame.callback_ns)
            self.mailbox.publish_timed(emitted, due, oldest, kind, frame.sequence, ready)
            self.generated += kind
            self.original += not kind
        r.current, r.previous = r.previous, r.current
        r.current_window,r.previous_window = r.previous_window,r.current_window
        r.valid = True
        if len(self.publish_ms) < 10000:
            self.publish_ms.append((time.perf_counter_ns()-began)/1e6)


def worker(*args, **kwargs):
    global CTX
    from screento3d_app import live_sbs, live_model
    model = kwargs.get("backend_snapshot", {}).get("model")
    if (len(args) < 9 or not isinstance(args[7], TimedMailbox)
            or model not in SUPPORTED_MODELS
            or not kwargs.get("gpu_capture_snapshot")):
        raise ValueError("VFG experiment requires Small/Base GPU window capture and native output")
    CTX = Producer(args[7], args[2])
    original_reset = live_sbs.reset_reason

    def reset_reason(*values, **options):
        reason = original_reset(*values, **options)
        CTX.last_reset = "cut" if values[-1] else reason
        CTX.resets += reason is not None
        if CTX.last_reset:
            CTX.reset_counts[CTX.last_reset] = CTX.reset_counts.get(CTX.last_reset,0)+1
        return reason

    def renderer(native, gpu_capture):
        if not native or not gpu_capture:
            raise ValueError("VFG cannot fall back to host output")
        return vfg_renderer(model)

    adapter = replace(live_model._MODELS[model], renderer=renderer)
    try:
        with patch.dict(live_model._MODELS, {model: adapter}), patch.object(live_sbs, "reset_reason", reset_reason):
            live_sbs.sbs_worker(*args, **kwargs)
    finally:
        path = Path(app_env_required('SCREENTO3D_VFG_EVIDENCE'))
        (path / f"worker-{os.getpid()}.json").write_text(json.dumps(dict(
            model=model, generated=CTX.generated, original=CTX.original, resets=CTX.resets,
            created=CTX.created, closed=CTX.closed, vfg_wall_ms=CTX.vfg_ms,
            publication_wall_ms=CTX.publish_ms, reset_counts=CTX.reset_counts,
            reset_base_ids=CTX.cut_bases), indent=2))
        CTX = None


class TimedDelivery(NativeDelivery):
    def __init__(self):
        super().__init__()
        self.records = {}
        self.visible = lambda: True
        self.on_published = lambda: None

    def begin(self, session):
        super().begin(session)
        self.records.clear()

    def consume(self, mailbox, owned_pid, *, cadence=None):
        delivery = self

        class Cadence:
            period_ns = 1  # One descriptor per poll; avoids same-poll replacement.

            def ready(self, now):
                pending = [f for f in mailbox.pending(delivery.pool.session, delivery.pool.generation)
                           if f.sequence > delivery.last_sequence]
                if not pending:
                    return False
                record = mailbox.frame_timing(pending[0])
                if record[1] > now or cadence is not None and not cadence.ready(now):
                    return False
                if delivery.visible() and delivery.has_frame:
                    submitted = delivery.report()["output"]["last_submitted_id"]
                    if submitted < delivery.last_sequence:
                        return False
                delivery.records[record[0]] = record
                if len(delivery.records) > 4096:
                    del delivery.records[min(delivery.records)]
                return True

            def emitted(self, now):
                if cadence is not None:
                    cadence.emitted(now)

        if self.pool is not None and mailbox.state() == RETIRING:
            # Retirement must consume/release all pending GPU leases, regardless of due times.
            return super().consume(mailbox, owned_pid)
        changed = super().consume(mailbox, owned_pid, cadence=Cadence())
        if changed:
            self.on_published()
        return changed


def install(enabled=True):
    """Call in the parent before starting the experimental session."""
    from screento3d_app import texture_mailbox, native_delivery, live_sbs
    texture_mailbox.TextureMailbox = TimedMailbox
    native_delivery.NativeDelivery = TimedDelivery
    if enabled:
        live_sbs.sbs_worker = worker
