"""Owned live controller: native SBS delivery with explicit host diagnostics."""
from .messages import ErrorMessage as E

from .messages import Message as M, message_value, decode_message, as_error
from .localization import localized, render

import multiprocessing as mp
import ctypes
import os
import time
from collections import deque
from statistics import median
from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot, Qt
from PySide6.QtGui import QImage, QGuiApplication
from PySide6.QtQuick import QQuickImageProvider

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
    MAX_BYTES,
    validate_shape,
)
from .capture_sources import monitors, windows, validate_source
from .capture_worker import capture_worker
from .live_sbs import SBS_REUSED, STAT_COUNT, GPU_USAGE, GPU_USAGE_NS, BACKGROUND_NS
from .live_policy import LIVE_MODES
from .live_backend import (
    choices as live_model_choices,
    default_model as default_live_model,
)
from .presentation_policy import PresentationCadence, delivery_cadence
from .frame_wakeup import FrameWakeup
from .owned_preview_image import PreviewCopyPool
from .stereo_layout import LAYOUTS

NATIVE_MODELS = ("da2-small", "da2-base", "vda-small", "ovda-small-c16")
DEFAULT_LIVE_STRENGTH = 0.5


class PreviewImages(QQuickImageProvider):
    def __init__(self):
        super().__init__(QQuickImageProvider.Image)
        self.image = QImage()
        self.requests = 0

    def requestImage(self, identifier, size, requestedSize):
        self.requests += 1
        size.setWidth(self.image.width())
        size.setHeight(self.image.height())
        return self.image


class LivePreview(QObject):
    vfg_configurable = True
    changed = Signal()
    frameChanged = Signal()
    errorOccurred = Signal(object)
    vfgNotification = Signal(str, bool)  # Message and whether preparation is pending.

    def reportError(self, message):
        self.stop_message_pending = False
        self.message = as_error(message)
        self.changed.emit()
        self.errorOccurred.emit(self.message)

    def __init__(self, desktop):
        super().__init__(desktop)
        self.desktop = desktop
        self.provider = PreviewImages()
        self.copy_pool = PreviewCopyPool()
        self.use_copy_pool = os.environ.get("DEPTHSBS_QT_COPY_POOL", "1") == "1"
        self.items = []
        self.kind = "window"
        self.selected = -1
        self.selection_required = False
        self.cursor = True
        self.process = self.mailbox = None
        self.capture_telemetry = None
        self.preparation = None
        self.stereo_renderer = 'cuda'
        self.gpu_capture_selected = False
        self.stopping = False
        self.stop_message_pending = False
        self.message = M('Select a window to view.')
        self.session = 0
        self.version = 0
        self.meta = [0] * 12
        self.submitted = self.presented = 0
        self.pending_present = None
        self.latencies = deque(maxlen=512)
        self.callback_latencies = deque(maxlen=512)
        self.started = self.last_health = self.last_stats = 0
        self.stop_started = 0
        self.ended = None
        self.source = None
        self.excluded = False
        self.preview_visible = True
        self.sbs = True
        selection = desktop.preferences.selection('live', LIVE_MODES)
        self.stereo_layout = selection['stereo_layout']
        self.mode = selection['mode']
        self.live_model = selection['model']
        self.ovda_noncommercial = False
        # Prepared local desktop default; explicit reference selection remains available.
        self.gpu_candidate = os.environ.get("DEPTHSBS_LIVE_GPU_CANDIDATE", "1") == "1"
        self.native_selected = self.gpu_candidate
        self.native = self.texture_mailbox = None
        self.cadence = PresentationCadence(60)
        self.strength = DEFAULT_LIVE_STRENGTH
        self.vfg_enabled = False
        self.vfg_switch = None
        self.transition_provider = PreviewImages()
        self.vfg_shortcut = ""
        self.vfg_notice = ""
        self.processing_stats = None
        self.final_processing_stats = [0] * STAT_COUNT
        self.output_window = None
        from .desktop_jobs import ROOT
        from .output_placement import OutputPlacement
        self.output_placement = OutputPlacement(ROOT / "out" / "desktop-output-placement.json")
        self._restore_output = False
        self.output_excluded = False
        self.output_presented = 0
        self.output_pending = None
        self.output_latencies = deque(maxlen=512)
        self.output_source_ns = 0
        self.output_samples = deque(maxlen=4096)
        self.gui_copy_ms = self.gui_notify_ms = 0.0
        self.notify_unlocked = os.environ.get("DEPTHSBS_QT_NOTIFY_UNLOCKED", "0") == "1"
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.setInterval(self.cadence.poll_ms)
        self.timer.timeout.connect(self.poll)
        self.native_wakeup = None
        self.delivery_timer = QTimer(self)
        self.delivery_timer.setTimerType(Qt.PreciseTimer)
        self.delivery_timer.setSingleShot(True)
        self.delivery_timer.timeout.connect(self.poll)
        self.poll_count = 0
        self.refresh()

    @Property("QVariantList", notify=changed)
    @localized
    def sources(self):
        return [dict(label=r["label"]) for r in self.items]

    @Property(str, notify=changed)
    @localized
    def sourceKind(self):
        return self.kind

    @Property(int, notify=changed)
    def selectedIndex(self):
        return self.selected

    @Property(str, notify=changed)
    @localized
    def sourceIcon(self):
        row = self.items[self.selected] if 0 <= self.selected < len(self.items) else {}
        if row.get("kind") != "window":
            return ""
        return f"image://windowicons/{row.get('id', 0)}/{row.get('pid', 0)}"

    @Property(bool, notify=changed)
    def cursorIncluded(self):
        return self.cursor

    @Property(bool, notify=changed)
    def active(self):
        return self.process is not None

    @Property(bool, notify=changed)
    def stoppingNow(self):
        return self.stopping

    @Property(str, notify=changed)
    @localized
    def status(self):
        return self.message

    @Property(str, notify=frameChanged)
    @localized
    def imageUrl(self):
        return (
            f"image://live/{self.session}/{self.version}"
            if not self.provider.image.isNull()
            else ""
        )

    @Property(str, notify=changed)
    @localized
    def metrics(self):
        if not self.started:
            return M('Capture —   Preview —   Queued frames 0 / 1')
        elapsed = max(0.001, (self.ended or time.perf_counter()) - self.started)
        age = sorted(self.latencies)
        p95 = f"{age[int((len(age) - 1) * 0.95)]:.1f} ms" if age else "—"
        main_count, output_count = self.submitted, self.output_presented
        if self.nativeEnabled:
            counts = self.native.report()
            main_count = counts["main"]["submitted_frames"]
            output_count = counts["output"]["submitted_frames"]
        return (
            M('Received {v0:.1f} fps  ·  Preview submitted {v1:.1f} fps\nSession average: processed {v2:.1f} fps · Output submitted {v3:.1f} fps · Latest-frame replacements {v4}\n{v5} {v6} × {v7}  ·  Recent receive-to-swap P95 {v8}\n', v0=self.meta[RECEIVED] / elapsed, v1=main_count / elapsed, v2=self._stats()[0] / elapsed, v3=output_count / elapsed, v4=self.meta[REPLACED], v5=LAYOUTS[self.stereo_layout] if self.sbs else M('Source'), v6=self.meta[WIDTH], v7=self.meta[HEIGHT], v8=p95)
            + (
                M('{v0} + CUDA · Processed {v1} · Input replacements {v2} · Resets {v3}\nRecent preprocessing/inference/SBS {v4:.1f}/{v5:.1f}/{v6:.1f} ms · Includes CPU delivery boundary', v0=self.liveModelLabel, v1=self._stats()[0], v2=self._stats()[1], v3=self._stats()[2], v4=self._stats()[3] / 1e6, v5=self._stats()[4] / 1e6, v6=self._stats()[5] / 1e6)
                if self.sbs
                else M('Source preview · CPU copy path · Output target {v0} fps', v0=self.cadence.hz)
            )
        )

    def _stats(self):
        return (
            list(self.processing_stats)
            if self.processing_stats is not None
            else self.final_processing_stats
        )

    @Property(bool, notify=changed)
    def sbsEnabled(self):
        return self.sbs

    @Property(float, notify=changed)
    def depthStrength(self):
        return self.strength

    @Property("QVariantList", notify=changed)
    def liveModes(self):
        from .model_presentation import selection_info
        return [dict(key=mode, label=selection_info(mode, default_live_model(mode), self.desktop.engine_paths)['label'])
                for mode in LIVE_MODES]

    @Property('QVariantList', notify=changed)
    @localized
    def depthChoices(self):
        from .desktop_jobs import PORTABLE_DESKTOP
        from .model_presentation import selection_choices
        return selection_choices(LIVE_MODES, self.desktop.engine_paths, portable=PORTABLE_DESKTOP)

    @Property(str, notify=changed)
    @localized
    def depthModelHelp(self):
        from .model_presentation import selection_info
        return selection_info(self.mode, self.live_model, self.desktop.engine_paths)['help']

    @Slot(str)
    def selectDepthModel(self, key):
        if self.active or self.desktop.busy:
            return
        selected = next((entry for entry in self.depthChoices if entry['key'] == key), None)
        if selected is not None:
            self.setMode(selected['mode'])
            self.setLiveModel(selected['model'])

    @Property("QVariantList", notify=changed)
    def liveModels(self):
        from .desktop_jobs import PORTABLE_DESKTOP
        return [
            dict(key=model, label=self.desktop.models_label(model))
            for model in live_model_choices(self.mode)
            if not (PORTABLE_DESKTOP and model == "ovda-small-c16")
        ]

    @Property(str, notify=changed)
    @localized
    def liveModel(self):
        return self.live_model

    @Property(str, notify=changed)
    @localized
    def liveModelLabel(self):
        return self.desktop.models_label(self.live_model)

    @Property(bool, notify=changed)
    def ovdaConfirmed(self):
        return self.ovda_noncommercial

    @Property(str, notify=changed)
    @localized
    def liveMode(self):
        return self.mode

    @Property(str, notify=changed)
    @localized
    def policyDescription(self):
        prefix = (
            M('Direct GPU output · Experimental · ')
            if self.nativeEnabled
            else M('GPU accelerated · Local default · ')
            if self.gpu_candidate
            else ""
        )
        return (
            prefix
            + LIVE_MODES[self.mode].description
            + M(' · Offline Quality is available for files only')
        )

    @Property(str, notify=changed)
    @localized
    def supportStatus(self):
        from .live_support import guidance

        if self.sbs and self.gpu_candidate:
            return M('Locally validated on RTX 5090 · Other GPUs need validation · No automatic scaling or model replacement · 60 fps is not guaranteed')

        if not self.sbs:
            return M('Source preview · Separate from live 3D performance measurements.')
        if self.active and self.meta[WIDTH]:
            return guidance(self.meta[WIDTH] // 2, self.meta[HEIGHT])
        if 0 <= self.selected < len(self.items):
            source = self.items[self.selected]
            return guidance(source["width"], source["height"])
        return guidance(0, 0)

    @Property(str, notify=changed)
    @localized
    def processingPath(self):
        if self.native_selected:
            return "gpu-texture"
        return "gpu" if self.gpu_candidate else "reference"

    @Property(bool, notify=changed)
    def nativeEnabled(self):
        return self.sbs and self.native_selected

    @Property(bool, notify=changed)
    def nativeReady(self):
        return self.native is not None

    @Property(bool, notify=changed)
    def nativeCapable(self):
        return self.sbs and self.live_model in NATIVE_MODELS

    @Property(int, notify=changed)
    def nativeSession(self):
        return self.session

    @Property(int, notify=frameChanged)
    def frameRevision(self):
        return self.version

    @Property(bool, notify=frameChanged)
    def hasFrame(self):
        if self.nativeEnabled:
            return self.active and not self.stopping and self.native is not None and self.native.has_frame
        return not self.provider.image.isNull()

    @Property(int, notify=changed)
    def presentationHz(self):
        return self.cadence.hz

    @Property(bool, notify=changed)
    def vfgEnabled(self):
        return self.vfg_enabled

    @Property(bool, constant=True)
    def vfgConfigurable(self):
        return self.vfg_configurable

    @Property(str, notify=changed)
    @localized
    def vfgUnavailableReason(self):
        return self._vfg_reason()

    def _vfg_reason(self):
        from .vfg_runtime import unavailable_reason
        return unavailable_reason(self.live_model, self.kind,
                                  self.nativeEnabled, self.gpu_candidate and
                                  os.environ.get('DEPTHSBS_GPU_CAPTURE', '1') != '0',
                                  os.environ.get('DEPTHSBS_STEREO_RENDERER', 'cuda'))

    @Property(str, notify=changed)
    @localized
    def vfgNoticeText(self):
        return self.vfg_notice

    def notifyVfg(self, message, pending):
        self.vfg_notice = message
        self.vfgNotification.emit(render(message), pending)

    @Slot(bool)
    def setVfg(self, enabled):
        if not self.vfg_configurable or self.vfg_switch is not None or enabled == self.vfg_enabled:
            return
        if self.stopping or self.desktop.closing or (self.desktop.busy and not self.active):
            return
        if enabled and self.vfgUnavailableReason:
            self.reportError(self._vfg_reason())
            return
        if self.active:
            try:
                if enabled:
                    from .vfg_runtime import validate_runtime
                    validate_runtime()
                self.notifyVfg("", False)
                image = (self.output_window.grabWindow()
                         if self.output_window is not None and self.output_window.isVisible()
                         and self.hasFrame else QImage())
                self.vfg_switch = dict(enabled=bool(enabled), source=dict(self.source),
                                       phase="stopping", aspect=self.outputAspect)
                self.transition_provider.image = image
                self.version += 1
                self.stop(switching=True)
                self.message = M('Enabling VFG…') if enabled else M('Disabling VFG…')
                self.stop_message_pending = False
                self.notifyVfg(M('Preparing VFG…') if enabled else M('Disabling VFG…'), True)
                self.frameChanged.emit()
                self.changed.emit()
            except Exception as error:
                self._cancel_vfg_switch()
                self.frameChanged.emit()
                self.reportError(error)
            return
        self.vfg_enabled = bool(enabled)
        self.changed.emit()

    @Slot()
    def toggleVfg(self):
        self.setVfg(not self.vfg_enabled)

    @Property(bool, notify=changed)
    def vfgSwitching(self):
        return self.vfg_switch is not None

    @Property(str, notify=changed)
    @localized
    def vfgShortcut(self):
        return self.vfg_shortcut

    @Property(str, notify=frameChanged)
    @localized
    def transitionImageUrl(self):
        return f"image://transition/{self.session}/{self.version}" if not self.transition_provider.image.isNull() else ""

    def _cancel_vfg_switch(self, *, completed=False):
        pending = self.vfg_switch
        self.vfg_switch = None
        self.transition_provider.image = QImage()
        self.notifyVfg(
            ("VFG ON" if pending["enabled"] else "VFG OFF") if completed and pending else "",
            False,
        )

    def _restart_vfg(self):
        pending = self.vfg_switch
        self.vfg_enabled = pending["enabled"]
        source = pending["source"]
        self.selected = next((i for i, item in enumerate(self.items)
                              if item.get("id") == source.get("id") and item.get("pid") == source.get("pid")), -1)
        if self.selected < 0:
            self.items.append(source)
            self.selected = len(self.items) - 1
        pending["phase"] = "starting"
        self.start()
        if not self.active:
            self._cancel_vfg_switch()
            self.frameChanged.emit()
            self.changed.emit()

    def notifyNativeFrame(self):
        self.version += 1
        self.notifyFrame()

    def closeNativeWakeup(self):
        self.delivery_timer.stop()
        if self.native_wakeup is not None:
            self.native_wakeup.close()
            self.native_wakeup.deleteLater()
            self.native_wakeup = None

    @Slot()
    def nativeFrameReady(self):
        if self.active and not self.stopping:
            self.poll()

    @Slot(str)
    def setProcessingPath(self, path):
        if self.active:
            return
        if path not in ("gpu", "reference", "gpu-texture"):
            self.reportError(E('E_LIVE_PATH_UNSUPPORTED'))
        elif path == "gpu-texture" and self.live_model not in NATIVE_MODELS:
            self.reportError(E('E_OUTPUT_GPU_UNSUPPORTED'))
        else:
            try:
                if path == "gpu-texture" and self.native is None:
                    from .native_delivery import NativeDelivery

                    self.native = NativeDelivery()
                self.native_selected = path == "gpu-texture"
                self.gpu_candidate = path != "reference"
            except Exception as error:
                self.reportError(E('E_OUTPUT_GPU_PREPARATION', v0=error))
        self.changed.emit()

    @Slot(int)
    def setPresentationHz(self, hz):
        if self.active:
            return
        try:
            self.cadence = PresentationCadence(hz)
            self.timer.setInterval(self.cadence.poll_ms)
        except ValueError as error:
            self.reportError(error)
        self.changed.emit()

    @Slot(str)
    def setMode(self, mode):
        if not self.active:
            if mode not in LIVE_MODES:
                self.reportError(E('E_LIVE_OFFLINE_SELECTION'))
            else:
                self.mode = mode
                if self.live_model not in live_model_choices(mode):
                    self.live_model = default_live_model(mode)
                    self.ovda_noncommercial = False
                if self.live_model not in NATIVE_MODELS:
                    self.native_selected = False
            self.changed.emit()

    @Slot(str)
    def setLiveModel(self, model):
        if not self.active and model in live_model_choices(self.mode):
            self.live_model = model
            self.ovda_noncommercial = False
            if model not in NATIVE_MODELS:
                self.native_selected = False
            self.changed.emit()

    @Slot(bool)
    def setOvdaConfirmed(self, confirmed):
        if not self.active and self.live_model == "ovda-small-c16":
            self.ovda_noncommercial = bool(confirmed)
            self.changed.emit()

    @Slot()
    def rememberSelection(self):
        # Only user activation calls this; diagnostic setters and comparison
        # launchers cannot overwrite ordinary app preferences.
        if not self.active and not self.desktop.busy and self.vfg_configurable:
            try:
                self.desktop.preferences.remember('live', self.mode, self.live_model, self.stereo_layout)
            except (ValueError, OSError) as error:
                self.reportError(error)

    @Property("QStringList", notify=changed)
    @localized
    def outputScreens(self):
        return [
            M('Monitor {v0} · {v1} · {v2} × {v3}', v0=index + 1, v1=screen.name(), v2=round(screen.size().width() * screen.devicePixelRatio()), v3=round(screen.size().height() * screen.devicePixelRatio()))
            + (M(' · Default') if screen == QGuiApplication.primaryScreen() else "")
            for index, screen in enumerate(QGuiApplication.screens())
        ]

    @Slot(bool)
    def setSbs(self, enabled):
        if not self.active:
            self.sbs = enabled
            self.changed.emit()

    @Slot(float)
    def setStrength(self, value):
        from .live_sbs import validate_strength

        if not self.active:
            self.strength = validate_strength(value)
            self.changed.emit()

    @Slot()
    def resetStrength(self):
        self.setStrength(DEFAULT_LIVE_STRENGTH)

    @Slot(int, bool)
    def requestOutput(self, index, fullscreen):
        try:
            self.showOutput(index, fullscreen)
        except Exception as error:
            if self.output_window is not None:
                self.output_window.hide()
            self.abort(error)

    @Slot(int, bool)
    def showOutput(self, index, fullscreen):
        from .output_placement import fit_rect

        screens = QGuiApplication.screens()
        if self.output_window is None or not 0 <= index < len(screens):
            return
        window = self.output_window
        window.setScreen(screens[index])
        if self._restore_output:
            window.setGeometry(fit_rect(self.output_placement.rect, screens[index].availableGeometry()))
        else:
            window.setPosition(screens[index].geometry().topLeft())
        if not self.configureOutputCapture(window):
            self.reportError(
                E('E_OUTPUT_CAPTURE_POLICY')
            )
            return
        window.showFullScreen() if fullscreen else window.showNormal()
        if not self.configureOutputCapture(window):
            window.hide()
            self.abort(E('E_OUTPUT_CAPTURE_POLICY_STOP'))

    def configureOutputCapture(self, window):
        from .capture_sources import set_output_affinity

        exclude = self.kind != 'window'
        applied = set_output_affinity(window.winId(), exclude)
        self.output_excluded = applied and exclude
        return applied

    @Slot()
    def rememberOutput(self):
        from PySide6.QtGui import QWindow

        window = self.output_window
        if window is not None and window.visibility() == QWindow.Windowed:
            self.output_placement.rect = window.geometry()
            self.output_placement.screen_name = window.screen().name()

    @Slot()
    def startMinimal(self):
        if self.active or self.desktop.busy:return
        if self.selected<0:
            self.errorOccurred.emit(E('E_CAPTURE_SOURCE_REQUIRED'));return
        source=dict(self.items[self.selected])
        selection=(self.mode,self.live_model,self.stereo_layout,self.vfg_enabled,self.strength)
        def resume():
            current=dict(self.items[self.selected]) if self.selected>=0 else None
            if current!=source or selection!=(self.mode,self.live_model,self.stereo_layout,self.vfg_enabled,self.strength):
                self.errorOccurred.emit(E('E_SETUP_SELECTION_CHANGED'));return
            self.startMinimal()
        try:
            if not self.desktop.ensureRuntime('live',resume,model=self.live_model,vfg=self.vfg_enabled):return
            self.desktop.syncRuntimes()
        except Exception as exc:
            self.errorOccurred.emit(as_error(exc));return
        screens = QGuiApplication.screens()
        main = getattr(self.desktop, "main_window", None)
        preferred = main.screen() if main is not None else QGuiApplication.primaryScreen()
        index = self.output_placement.screen_index(screens, preferred)
        self._restore_output = True
        try:
            self.startSbs(0, index)
        finally:
            self._restore_output = False

    @Slot(result=str)
    @localized
    def outputSummary(self):
        now = time.perf_counter_ns()
        seconds = min(2.0, (now / 1e9 - self.started)) if self.started else 0
        since = now - 2_000_000_000
        if self.nativeEnabled and self.native is not None:
            samples = self.native.recent_output(since)
        else:
            samples = [s for s in self.output_samples if s[0] >= since]
        originals = [s for s in samples if s[2] == 0]
        def rate(count):
            return f"{count / seconds:.0f}" if seconds > 0 and self.active else "—"
        ages = [(end - source) / 1e6 for end, source, _ in originals if source > 0]
        delay = f"{median(ages):.0f} ms" if ages else "—"
        from .gpu_usage import usage_text
        stats = self._stats()
        gpu = usage_text(stats[GPU_USAGE], stats[GPU_USAGE_NS], now, active=self.active)
        return (M('Source {v0} · Output {v1} · Interpolated {v2} fps · Latency {v3} · {v4}', v0=rate(len(originals)), v1=rate(len(samples)), v2=rate(len(samples) - len(originals)), v3=delay, v4=gpu))

    @Property(float, notify=changed)
    def outputAspect(self):
        if self.meta[HEIGHT]:
            return self.meta[WIDTH] / self.meta[HEIGHT]
        return self.vfg_switch.get("aspect", 0) if self.vfg_switch is not None else 0

    @Property(str, notify=changed)
    @localized
    def stereoLayout(self):
        return self.stereo_layout

    @Property(str, notify=changed)
    @localized
    def stereoLayoutLabel(self):
        return LAYOUTS[self.stereo_layout]

    @Slot(str)
    def setStereoLayout(self, layout):
        from .stereo_layout import LAYOUTS
        if not self.active and layout in LAYOUTS:
            self.stereo_layout = layout
            self.changed.emit()

    @Slot()
    def outputFrameSwapped(self):
        if (
            self.output_pending is not None
            and self.active
            and not self.stopping
            and self.output_window.isVisible()
        ):
            self.output_presented += 1
            self.output_samples.append((time.perf_counter_ns(), self.output_source_ns, 0))
            self.output_latencies.append(
                (time.perf_counter_ns() - self.output_pending) / 1e6
            )
            self.output_pending = None

    @Slot()
    def outputVisibilityChanged(self):
        if self.output_window is not None and self.output_window.isVisible():
            if not self.configureOutputCapture(self.output_window):
                self.output_window.hide()
                self.abort(E('E_OUTPUT_CAPTURE_POLICY_STOP'))
        else:
            self.output_pending = None

    @Slot()
    def screensChanged(self):
        # Capture/GPU topology still needs a new validated session. Restore a
        # visible control window rather than leaving the user on a lost display.
        if self.output_window is not None and self.output_window.isVisible():
            self.abort(E('E_OUTPUT_DISPLAY_CHANGED'))
            if not self.active:
                self.output_window.hide()
        main = getattr(self.desktop, "main_window", None)
        if main is not None and QGuiApplication.screens():
            files=bool(main.property('fileWorkspace'))
            self.desktop.fitControlWindow(main,760 if files else 380,620 if files else 260,main.width(),main.height())
            main.showNormal()
        self.changed.emit()

    @Slot(str)
    def setKind(self, kind):
        if not self.active and kind in ("window", "monitor"):
            if kind != self.kind:
                self.items, self.selected = [], -1
                self.selection_required = False
            self.kind = kind
            self.message = M('Select a window to view.') if kind == "window" else M('Select a monitor to view.')
            self.refresh()

    @Slot(int)
    def select(self, index):
        if not self.active and 0 <= index < len(self.items):
            self.selected = index
            self.selection_required = False
            self.message = M('Ready to start')
            self.changed.emit()

    @Slot(bool)
    def setCursor(self, enabled):
        if not self.active:
            self.cursor = enabled
            self.changed.emit()

    @Slot()
    def refresh(self):
        if self.active:
            return
        previous = (
            self.items[self.selected] if 0 <= self.selected < len(self.items) else None
        )

        def identity(row):
            # Titles and enumeration order can change. HWND + PID guards reuse;
            # monitor device names survive enumeration-order changes.
            if row.get("kind") == "monitor":
                return ("monitor", row.get("device"))
            return (row.get("kind"), row.get("id"), row.get("pid"))

        try:
            self.items = windows() if self.kind == "window" else monitors()
            if previous is not None:
                self.selected = next(
                    (i for i, row in enumerate(self.items) if identity(row) == identity(previous)),
                    -1,
                )
                if self.selected < 0:
                    self.selection_required = True
                    self.message = M('The selected source disappeared from the list. Select the capture source again.')
            else:
                self.selected = -1
            if not self.items:
                self.message = M('No sources are available. Open the app you want to view, then reopen the list.')
        except Exception as error:
            self.selection_required = self.selection_required or previous is not None
            self.items, self.selected = [], -1
            self.reportError(error)
        self.changed.emit()

    @Slot(bool)
    def setPreviewVisible(self, visible):
        self.preview_visible = visible
        if not visible:
            self.pending_present = None

    @Slot(int, int)
    def startSbs(self, output_style, screen_index):
        """User-facing start; capture-only remains a diagnostic API, never a mode."""
        if self.active or self.desktop.busy:
            self.reportError(
                E('E_LIVE_ALREADY_RUNNING')
                if self.active else E('E_LIVE_TASK_BUSY')
            )
            return
        if not 0 <= self.selected < len(self.items):
            self.reportError(E('E_LIVE_SOURCE_REQUIRED'))
            return
        if output_style not in (0, 1, 2) or (
            output_style != 2 and not 0 <= screen_index < len(QGuiApplication.screens())
        ):
            self.reportError(E('E_OUTPUT_DISPLAY_REQUIRED'))
            return
        self.setSbs(True)
        self.message = M('Preparing live 3D… Checking the capture source and output display.')
        self.changed.emit()
        self.start()
        try:
            if self.active and output_style != 2:
                self.showOutput(screen_index, output_style == 1)
                if not self.stopping and (
                    self.output_window is None or not self.output_window.isVisible()
                ):
                    self.abort(E('E_OUTPUT_WINDOW_FAILED'))
            elif self.active and self.output_window is not None:
                self.output_window.hide()
        except Exception as error:
            self.abort(E('E_OUTPUT_PREPARATION_FAILED', v0=error))

    @Slot()
    def start(self):
        if self.active or self.desktop.busy:
            return
        try:
            if self.desktop.gpuRuntimeKey and self.desktop.downloads.needed(self.desktop.gpuRuntimeKey):
                raise ValueError(E('E_GPU_RUNTIME_REQUIRED'))
            if self.selected < 0:
                raise ValueError(E('E_CAPTURE_SOURCE_REQUIRED'))
            source = dict(self.items[self.selected])
            validate_source(source)
            validate_shape(source["width"], source["height"])
            backend_snapshot = {
                "model": self.live_model,
                "engine": self.desktop.engine_paths.get(self.live_model, ""),
                "runtime": self.desktop.values["runtime"],
                "noncommercial": self.ovda_noncommercial,
            }
            from .live_backend import validate_snapshot

            validate_snapshot(backend_snapshot, self.mode)
            from .live_sbs import resolve_gpu_capture, resolve_renderer
            from .vfg_runtime import validate_selection
            self.gpu_capture_selected = self.sbs and resolve_gpu_capture(source, self.live_model, self.gpu_candidate)
            self.stereo_renderer = resolve_renderer(self.live_model, self.gpu_candidate, self.strength) if self.sbs else 'cuda'
            validate_selection(self.vfg_enabled, self.live_model, source['kind'],
                               self.nativeEnabled, self.gpu_capture_selected, self.stereo_renderer)
            if self.nativeEnabled and self.live_model not in NATIVE_MODELS:
                raise ValueError(
                    E('E_OUTPUT_GPU_UNSUPPORTED')
                )
            if source["kind"] == "monitor" and not self.excluded:
                raise ValueError(
                    E('E_CAPTURE_RECURSION_UNSAFE')
                )
            self.desktop.lease.acquire("live")
            context = mp.get_context("spawn")
            telemetry_setting = os.environ.get("DEPTHSBS_CAPTURE_TELEMETRY", "0")
            if telemetry_setting not in ("0", "1"):
                raise ValueError("DEPTHSBS_CAPTURE_TELEMETRY must be 0 or 1")
            self.capture_telemetry = None
            if telemetry_setting == "1":
                from .capture_telemetry import CaptureTelemetry

                self.capture_telemetry = CaptureTelemetry.create(context)
            self.texture_mailbox = None
            self.closeNativeWakeup()
            self.cadence = delivery_cadence(self.cadence.hz, native=self.nativeEnabled, vfg=self.vfg_enabled)
            if self.nativeEnabled:
                from .texture_mailbox import TextureMailbox

                if self.vfg_enabled:
                    from .vfg_delivery import TimedMailbox, TimedDelivery
                    if not isinstance(self.native, TimedDelivery):
                        if self.native is not None:
                            self.native.end()
                        self.native = TimedDelivery()
                    self.native.visible = lambda: self.output_window is not None and self.output_window.isVisible()
                    TextureMailbox = TimedMailbox
                elif getattr(self.native, 'vfg_delivery', False):
                    self.native.end()
                    self.native = None

                if self.native is None:
                    from .native_delivery import NativeDelivery
                    try:
                        self.native = NativeDelivery()
                    except Exception as error:
                        raise RuntimeError(
                            E('E_OUTPUT_GPU_PREPARATION_HINT', v0=error)
                        ) from error
                self.native.begin(self.session + 1)
                self.texture_mailbox = TextureMailbox.create(context)
                self.native_wakeup = FrameWakeup(self)
                self.native_wakeup.ready.connect(self.nativeFrameReady)
                self.native_wakeup.failed.connect(self.abort)
                self.texture_mailbox.wake_writer = self.native_wakeup.writer
            self.mailbox = Mailbox.create(
                context, sbs=self.sbs, metadata_only=self.nativeEnabled
            )
            self.processing_stats = context.RawArray(ctypes.c_longlong, STAT_COUNT)
            from .live_sbs import sbs_worker, resolve_gpu_capture, resolve_renderer
            self.gpu_capture_selected = self.sbs and resolve_gpu_capture(source, self.live_model, self.gpu_candidate)
            self.stereo_renderer = resolve_renderer(self.live_model,self.gpu_candidate,self.strength) if self.sbs else 'cuda'
            # Advisory single-writer status must not leave a lock held on cancellation.
            self.preparation = context.Array(ctypes.c_char,512,lock=False) if self.stereo_renderer=='rowflow-sym' else None

            self.process = context.Process(
                target=sbs_worker if self.sbs else capture_worker,
                args=(
                    source,
                    self.cursor,
                    self.mailbox,
                    self.processing_stats,
                    self.strength,
                    self.mode,
                    self.gpu_candidate,
                    *(
                        [self.texture_mailbox, self.session + 1]
                        if self.nativeEnabled
                        else []
                    ),
                )
                if self.sbs
                else (source, self.cursor, self.mailbox),
                kwargs={
                    "capture_telemetry": self.capture_telemetry,
                    **({"backend_snapshot": backend_snapshot, "gpu_capture_snapshot": self.gpu_capture_selected,
                        "renderer_snapshot": self.stereo_renderer,"preparation": self.preparation,
                        "vfg_enabled": self.vfg_enabled,"output_hz": self.cadence.hz,
                        "stereo_layout": self.stereo_layout} if self.sbs else {}),
                },
                daemon=True,
            )
            self.process.start()
            self.source = source
            self.session += 1
            self.version = self.submitted = self.presented = 0
            self.output_presented = 0
            self.output_pending = None
            self.output_latencies.clear()
            self.output_samples.clear()
            self.meta = [0] * 12
            self.latencies.clear()
            self.callback_latencies.clear()
            self.pending_present = None
            self.started = time.perf_counter()
            self.cadence.next_ns = 0
            self.ended = None
            self.last_health = self.last_stats = self.started
            self.stopping = False
            self.poll_count = 0
            self.message = M('Starting capture… Your screen is not being recorded.')
            self.timer.setInterval(self.native_wakeup.health_interval_ms if self.native_wakeup else self.cadence.poll_ms)
            self.timer.start()
        except Exception as error:
            self.closeNativeWakeup()
            if self.nativeEnabled and self.native is not None:
                self.native.end()
            if self.desktop.lease.owner == "live":
                self.desktop.lease.release("live")
            self.process = self.mailbox = None
            if self.output_window is not None:
                self.output_window.hide()
            self.reportError(error)
        self.desktop.changed.emit()
        self.changed.emit()

    @Slot()
    def stop(self, *, switching=False):
        if not switching:
            was_switching = self.vfgSwitching
            self._cancel_vfg_switch()
            if self.output_window is not None and (not self.active or self.stopping):
                self.output_window.hide()
            if was_switching:
                self.frameChanged.emit()
                self.changed.emit()
        if self.active and not self.stopping:
            self.delivery_timer.stop()
            self.rememberOutput()
            self.output_placement.save()
            if self.output_window is not None and not switching:
                self.output_window.hide()
            self.stopping = True
            self.stop_started = time.perf_counter()
            self.mailbox.stop.set()
            if self.nativeEnabled:
                self.native.end()
            self.provider.image = QImage()
            self.copy_pool.clear()
            self.output_pending = None
            self.pending_present = None
            self.frameChanged.emit()
            self.message = M('Stopping capture…')
            self.stop_message_pending = True
            self.changed.emit()

    def abort(self, message):
        self.stop()
        self.reportError(message)

    def poll(self):
        if not self.active:
            return
        self.poll_count += 1
        self.delivery_timer.stop()
        now = time.perf_counter()
        if not self.process.is_alive():
            if self.nativeEnabled:
                self.native.end()
            # Child has exited: metadata is stable even if a crash held its lock.
            self.meta = list(self.mailbox.meta)
            code = self.process.exitcode
            failure = None
            restart = self.vfg_switch is not None and self.vfg_switch["phase"] == "stopping" and code == 0 and not self.desktop.closing
            if not self.stopping:
                error = decode_message(bytes(self.mailbox.error.value))
                self.message = (
                    error or E('E_CAPTURE_STOPPED', v0=code)
                )
                failure = self.message
            elif self.stop_message_pending:
                self.message = M('Live 3D stopped.')
            self.stop_message_pending = False
            self.process.join(timeout=0)
            self.process.close()
            self.closeNativeWakeup()
            self.final_processing_stats = self._stats()
            self.processing_stats = None
            self.process = self.mailbox = None
            self.texture_mailbox = None
            self.preparation = None
            self.provider.image = QImage()
            self.copy_pool.clear()
            self.output_pending = None
            self.ended = now
            self.pending_present = None
            self.timer.stop()
            self.desktop.lease.release("live")
            self.stopping = False
            if restart:
                self._restart_vfg()
                return
            if self.vfg_switch is not None:
                self._cancel_vfg_switch()
                if self.output_window is not None:
                    self.output_window.hide()
                failure = failure or E('E_VFG_TRANSITION')
            self.frameChanged.emit()
            self.changed.emit()
            self.desktop.changed.emit()
            if failure is not None:
                self.reportError(failure)
            if self.desktop.closing:
                self.desktop.exitReady.emit()
            return
        if self.stopping:
            if now - self.stop_started > 5:
                if self.vfg_switch is not None:
                    self._cancel_vfg_switch()
                    if self.output_window is not None:
                        self.output_window.hide()
                # Only this session's isolated worker. No output files to lose.
                self.process.terminate()
                if self.preparation is not None and self.preparation.value:
                    # Synchronous compiler work is cancelled with its owned job.
                    self.message = M('Stereo preparation cancelled.')
                    self.stop_message_pending = False
                    self.changed.emit()
                    return
                message = E('E_CAPTURE_TIMEOUT')
                if self.message != message:
                    self.reportError(message)
            return
        if self.preparation is not None and self.preparation.value:
            message = decode_message(bytes(self.preparation.value))
            if self.message!=message:
                self.message=message
                self.changed.emit()
        if now - self.last_health > 0.25:
            self.last_health = now
            try:
                validate_source(self.source)
            except Exception as error:
                self.abort(error)
                return
            if not self.meta[RECEIVED] and now - self.started > (
                120 if self.sbs else 10
            ):
                self.abort(
                    E('E_CAPTURE_NO_FRAMES')
                )
                return
        notify = False
        if self.nativeEnabled:
            try:
                native_changed = self.native.consume(
                    self.texture_mailbox, self.process.pid, cadence=self.cadence
                )
                if native_changed:
                    # Publication can happen after the worker's statistics were
                    # acknowledged. Wake the surface for the actual broker frame,
                    # including timed VFG and retirement, not for that metadata.
                    if self.vfg_switch is not None and self.vfg_switch["phase"] == "starting" and self.native.has_frame:
                        self._cancel_vfg_switch(completed=True)
                        self.changed.emit()
                    self.notifyNativeFrame()
            except Exception as error:
                self.abort(E('E_OUTPUT_FRAME_DELIVERY', v0=error))
                return
        if (self.nativeEnabled or self.cadence.ready(time.perf_counter_ns())) and self.mailbox.lock.acquire(
            False
        ):
            try:
                m = self.mailbox.meta
                self.meta = list(m)
                if m[STATE] == FAILED:
                    error = decode_message(bytes(self.mailbox.error.value))
                else:
                    error = None
                visible = self.preview_visible or (
                    self.output_window is not None and self.output_window.isVisible()
                )
                if not error and visible and m[SEQ] > m[ACK]:
                    w, h = m[WIDTH], m[HEIGHT]
                    # Owned copy before releasing cross-process lock. No native
                    # mapped view survives callback or mailbox ownership.
                    copy_started = time.perf_counter_ns()
                    self.provider.image = (
                        QImage()
                        if self.nativeEnabled
                        else (
                            self.copy_pool.copy(self.mailbox.pixels, w, h)
                            if self.use_copy_pool
                            else QImage(
                                self.mailbox.pixels, w, h, w * 4, QImage.Format_RGB32
                            ).copy()
                        )
                    )
                    self.gui_copy_ms = (
                        0
                        if self.nativeEnabled
                        else (time.perf_counter_ns() - copy_started) / 1e6
                    )
                    m[ACK] = m[SEQ]
                    self.meta[ACK] = m[ACK]
                    if not self.nativeEnabled:
                        self.version += 1
                    self.submitted += 1
                    self.pending_present = (
                        None if self.nativeEnabled else (m[CALLBACK_NS], m[SOURCE_NS])
                    )
                    self.output_pending = (
                        m[CALLBACK_NS]
                        if not self.nativeEnabled
                        and self.output_window is not None
                        and self.output_window.isVisible()
                        else None
                    )
                    self.output_source_ns = m[SOURCE_NS]
                    self.message = (
                        (M('● Direct GPU output · VFG 2× / Not recording') if self.vfg_enabled
                         else M('● Direct GPU output · Experimental / Not recording'))
                        if self.nativeEnabled
                        else M('● {v0} live {v1} / Not recording', v0=self.liveModelLabel, v1=LAYOUTS[self.stereo_layout])
                        if self.sbs
                        else M('● Capturing · Source preview / Not recording')
                    )
                    if not self.nativeEnabled:
                        if self.notify_unlocked:
                            notify = True
                        else:
                            self.notifyFrame()
            except Exception as failure:
                error = E('E_FRAME_DELIVERY', v0=failure)
            finally:
                self.mailbox.lock.release()
            if error:
                self.abort(error)
                return
        if notify:
            self.notifyFrame()
        if now - self.last_stats > 0.5:
            self.last_stats = now
            self.changed.emit()
        if self.nativeEnabled and self.native_wakeup is not None and self.native_wakeup.event_driven and not self.stopping:
            try:
                delay = self.native.next_poll_delay_ns(self.texture_mailbox, self.cadence, time.perf_counter_ns())
                if delay is not None:
                    self.delivery_timer.start(max(1, (delay + 999_999) // 1_000_000))
            except Exception as error:
                self.abort(E('E_OUTPUT_WAIT_FAILED', v0=error))

    def notifyFrame(self):
        began = time.perf_counter_ns()
        self.frameChanged.emit()
        self.gui_notify_ms = (time.perf_counter_ns() - began) / 1e6
        if not self.nativeEnabled:
            self.cadence.emitted(time.perf_counter_ns())

    @Slot()
    def frameSwapped(self):
        if (
            self.pending_present is not None
            and self.active
            and not self.stopping
            and self.preview_visible
        ):
            callback, source = self.pending_present
            self.pending_present = None
            now = time.perf_counter_ns()
            self.presented += 1
            self.latencies.append((now - callback) / 1e6)
            if 0 <= now - source < 60_000_000_000:
                self.callback_latencies.append((now - source) / 1e6)

    def report(self):
        fused_live = self.live_model == "da2-small" and self.gpu_candidate
        source_device_live = (
            self.live_model in NATIVE_MODELS and self.live_model != "da2-small"
            and self.gpu_candidate
        )
        gpu_live = fused_live or source_device_live
        plan = (
            LIVE_MODES[self.mode].describe(self.strength, self.live_model)
            if self.sbs
            else None
        )
        if plan is not None:
            plan["live"]["presentation_hz"] = self.cadence.hz
        return dict(
            stereo_renderer=self.stereo_renderer,
            learned_renderer_contract=(
                'RowFlow v3 symmetric; fixed-shape fullgraph compile; FP16 autocast; '
                'divergence=100*policy.divergence; convergence=policy.convergence; '
                'steps=1; standard left/right eye order; CUDA conservative coverage flag not used; '
                'owned RGB/depth GPU copies and finite scalar readbacks'
                if self.stereo_renderer=='rowflow-sym' else None
            ),
            projection_timing_scope='splat/resolve/copy' if self.stereo_renderer=='cuda' else 'not applicable to learned renderer; use overall SBS timing',
            received=self.meta[RECEIVED],
            received_scope="Capture sequence forwarded by worker and cached by GUI",
            capture_telemetry=self.capture_telemetry.snapshot()
            if self.capture_telemetry is not None
            else None,
            replaced=self.meta[REPLACED],
            contention=self.meta[CONTENTION],
            submitted=self.submitted,
            qt_delivery=dict(
                copy_pool=self.use_copy_pool,
                copy_ms=self.gui_copy_ms,
                notify_ms=self.gui_notify_ms,
                provider_requests=self.provider.requests,
                notify_unlocked=self.notify_unlocked,
            ),
            native_delivery=self.native.report() if self.nativeEnabled and self.native is not None else None,
            frame_swaps=self.presented,
            output_frame_swaps=self.output_presented,
            output_callback_to_swap_ms=list(self.output_latencies),
            processed_frames=self._stats()[0],
            stereo_layout=self.stereo_layout,
            inference_frames=self._stats()[10],
            reused_depth_frames=self._stats()[11],
            reused_sbs_frames=self._stats()[SBS_REUSED],
            plan=plan,
            processing_path="gpu-texture"
            if self.nativeEnabled
            else "gpu-candidate"
            if self.sbs and fused_live
            else "model-device-depth-gpu-stereo-host-output"
            if self.sbs and source_device_live
            else "model-host-depth-cuda-stereo"
            if self.sbs and self.live_model != "da2-small"
            else "reference-host-bridge",
            presentation_target_hz=self.cadence.hz,
            presentation_poll_ms=self.timer.interval(),
            delivery_polls=self.poll_count,
            delivery_event_driven=self.native_wakeup is not None and self.native_wakeup.event_driven,
            delivery_poll_scope="Native timer is health fallback; frame-ready and deadline wakeups are separate" if self.native_wakeup and self.native_wakeup.event_driven else "Periodic delivery poll",
            stage_timing_scope=(
                "candidate depth is submission; stereo includes pending GPU work"
                if fused_live
                else "synchronous model inference; stereo includes GPU post/projection completion"
                if source_device_live
                else "synchronous host stages"
            ),
            processing_stats=self._stats(),
            projection_stage_ms={
                name: self._stats()[index] / 1e6
                for index, name in enumerate(
                    (
                        "left_splat",
                        "left_resolve",
                        "left_pack" if self.nativeEnabled else "left_d2h",
                        "right_splat",
                        "right_resolve",
                        "right_pack" if self.nativeEnabled else "right_d2h",
                    ),
                    24,
                )
            }
            if fused_live
            else None,
            host_bridge_timing_scope="input ownership through shared output publication; excludes source wait and Qt",
            host_bridge_ms={
                name: self._stats()[index] / 1e6
                for index, name in enumerate(
                    ("input_copy", "input_color", "output_color", "output_copy"), 20
                )
            },
            gpu_stage_timing_available=fused_live,
            gpu_stage_timing_scope=(
                "Measured stream intervals including enqueue gaps; not GPU utilization"
                if fused_live else "Unavailable for the source-depth adapter; not zero cost"
            ),
            background_ms=self._stats()[BACKGROUND_NS] / 1e6 if gpu_live else None,
            gpu_stage_ms={
                name: self._stats()[index] / 1e6
                for index, name in enumerate(
                    (
                        "input_gpu_resize_normalize" if self.gpu_capture_selected else "input_h2d_normalize",
                        "inference_stream_interval",
                        "rgb_device_copy_depth_resize" if self.gpu_capture_selected else "rgb_h2d_depth_resize",
                        "sort_bounds",
                        "normalize_temporal",
                        "guide",
                        "projection_publish"
                        if self.nativeEnabled
                        else "projection_d2h",
                        "cpu_background",
                    ),
                    12,
                )
            }
            if fused_live
            else None,
            explicit_cuda_h2d_bytes=self._stats()[7],
            explicit_cuda_d2h_bytes=self._stats()[8],
            explicit_cuda_syncs=self._stats()[9],
            zero_copy=False,
            qt_d3d_no_vblank_thread=os.environ.get("QT_D3D_NO_VBLANK_THREAD", "0"),
            resizes=self.meta[RESIZES],
            width=self.meta[WIDTH],
            height=self.meta[HEIGHT],
            mailbox_slots=2 if self.sbs else 1,
            pending_frame=int(self.meta[SEQ] > self.meta[ACK]),
            shared_pixel_bytes=(
                0 if self.nativeEnabled else 2 * MAX_BYTES if self.sbs else MAX_BYTES
            ),
            callback_to_swap_ms=list(self.latencies),
            source_to_swap_unverified_ms=list(self.callback_latencies),
            source_clock="WGC SystemRelativeTime; cross-clock comparability requires oracle",
            last_callback_copy_ns=self.meta[COPY_NS],
            duration_seconds=(self.ended or time.perf_counter()) - self.started,
            copies=(
                ('WGC/D3D11/CUDA device copies + GPU preprocessing; thumbnail/border D2H; conditional background RGB/depth D2H and refined-depth H2D; '
                 + ('GPU SBS surface + per-window GPU copy' if self.nativeEnabled else 'SBS RGB D2H + owned BGRA/QImage + Qt upload'))
                if self.gpu_capture_selected
                else "capture readback + retained mapped BGRA + RGB/preprocess H2D; GPU SBS surface + per-window GPU copy; 4-byte validity D2H and eligible background depth D2H/H2D"
                if self.nativeEnabled
                else "native GPU readback + shared output BGRA copy + owned QImage copy + Qt upload"
                + (
                    "; uint8 resized input H2D + RGB H2D + same-stream device depth/postprocess/projection + RGB D2H; eligible flat backgrounds use explicit aligned-depth D2H/H2D"
                    if self.sbs and gpu_live
                    else "; TensorRT H2D/D2H + CUDA projection H2D/D2H + RGB/BGRA host conversion + owned input copy"
                    if self.sbs
                    else ""
                )
            ),
            note="FrameSwapped is Qt presentation submission, not physical display latency",
        )
