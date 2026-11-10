"""Worker-owned VFG rendering and publication. Enabled only by a session snapshot."""
import ctypes as ct
import os
import threading
import time

from .live_source_gpu_candidate import LiveSourceGpuCandidate
from .live_texture_pool import LiveTexturePool
from .texture_mailbox import TextureFrame
from .vfg_delivery import Timeline
from .vfg_runtime import BRIDGE, BRIDGE_HASH, validate_runtime

LAYOUT_HASH = "0394a7b790c92db37aaa49190e213edc65914e79625f03d38d62cf3c2911da85"
SMALL_LAYOUT_HASH = "d8cbabe89c36a7c3b224f8eb07cb3f458c92fb4e04280c55530f4b8d2db12849"

class BridgePool(LiveTexturePool):
    library_path = BRIDGE
    library_sha256 = BRIDGE_HASH


class VfgOutputMixin:
    requires_texture_slot = False  # _project writes only its owned linear RGBA buffer.

    def __init__(self, width, height, policy, engine, *, diagnostic=False):
        self.pool = self.vfg = self.current = self.previous = self.middle = None
        self.current_window = self.previous_window = None
        self.dll_dirs = []
        self.sdk_modules = []
        self.previous_vfx_path = os.environ.get('NV_VIDEO_EFFECTS_PATH')
        self.valid = False
        self.timeline = Timeline()
        self.slot = 0
        if self.library_sha256 != self.expected_layout or policy.depth_backend != self.expected_model:
            raise ValueError("VFG requires its model's pinned renderer layout")
        super().__init__(width, height, policy, engine)
        try:
            sdk, bridge = validate_runtime()
            for folder in (sdk / "bin", sdk / "features/nvvfxvideoframegeneration/bin"):
                self.dll_dirs.append(os.add_dll_directory(str(folder)))
            os.environ["NV_VIDEO_EFFECTS_PATH"] = str(sdk / "bin")
            # The NVIDIA proxy also loads components by basename. Establish
            # the validated identities before the proxy makes its first call.
            for name in ('bin/NVVideoEffects.dll', 'bin/NVCVImage.dll',
                         'features/nvvfxvideoframegeneration/bin/nvVFXVideoFrameGeneration.dll'):
                self.sdk_modules.append(ct.WinDLL(str(sdk / name)))
            self.bridge = ct.CDLL(str(bridge))
            self.bridge.live_texture_error.restype = ct.c_char_p
            self.bridge.vfg_create.argtypes = [ct.c_int, ct.c_int, ct.c_void_p]
            self.bridge.vfg_create.restype = ct.c_void_p
            self.bridge.vfg_destroy.argtypes = [ct.c_void_p]
            self.bridge.vfg_run.argtypes = [ct.c_void_p] * 4
            self.bridge.vfg_window_capture.argtypes = [ct.c_void_p] * 2
            self.bridge.vfg_window_apply.argtypes = [ct.c_void_p] * 4
            self.bridge.vfg_project.argtypes = [ct.c_void_p] * 2 + [ct.c_float] * 2 + [ct.c_int, ct.c_void_p]
            self.bridge.vfg_publish.argtypes = [ct.c_void_p] * 2 + [ct.c_int] * 3 + [ct.c_void_p]
            self.pool = BridgePool(width, height, diagnostic=diagnostic, layout=policy.stereo_layout)
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
        if self.previous_vfx_path is None:
            os.environ.pop('NV_VIDEO_EFFECTS_PATH', None)
        else:
            os.environ['NV_VIDEO_EFFECTS_PATH'] = self.previous_vfx_path
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
        from .live_small_gpu_input import LiveSmallGpuInput

        class SmallVfgRenderer(VfgOutputMixin, LiveSmallGpuInput):
            expected_model = 'da2-small'
            expected_layout = SMALL_LAYOUT_HASH

        return SmallVfgRenderer
    raise ValueError('Unsupported VFG depth model')


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
