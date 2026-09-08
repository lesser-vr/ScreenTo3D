"""Owned live controller: default host images or explicit native SBS delivery."""

import multiprocessing as mp
import ctypes
import os
import time
from collections import deque
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
from .live_sbs import STAT_COUNT
from .live_policy import LIVE_MODES
from .live_backend import choices as live_model_choices, default_model as default_live_model
from .presentation_policy import PresentationCadence
from .owned_preview_image import PreviewCopyPool


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
    changed = Signal()
    frameChanged = Signal()

    def __init__(self, desktop):
        super().__init__(desktop)
        self.desktop = desktop
        self.provider = PreviewImages()
        self.copy_pool = PreviewCopyPool()
        self.use_copy_pool = os.environ.get("DEPTHSBS_QT_COPY_POOL", "1") == "1"
        self.items = []
        self.kind = "window"
        self.selected = -1
        self.cursor = True
        self.process = self.mailbox = None
        self.capture_telemetry = None
        self.stopping = False
        self.message = "원본 미리보기 · 아직 SBS 변환하지 않습니다."
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
        self.sbs = False
        self.mode = "balanced"
        self.live_model = default_live_model(self.mode)
        self.ovda_noncommercial = False
        # Prepared local desktop default; explicit reference selection remains available.
        self.gpu_candidate = os.environ.get("DEPTHSBS_LIVE_GPU_CANDIDATE", "1") == "1"
        self.native_selected = False
        self.native = self.texture_mailbox = None
        self.cadence = PresentationCadence(30)
        self.strength = 1.0
        self.processing_stats = None
        self.final_processing_stats = [0] * STAT_COUNT
        self.output_window = None
        self.output_excluded = False
        self.output_presented = 0
        self.output_pending = None
        self.output_latencies = deque(maxlen=512)
        self.gui_copy_ms = self.gui_notify_ms = 0.0
        self.notify_unlocked = os.environ.get("DEPTHSBS_QT_NOTIFY_UNLOCKED", "0") == "1"
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.setInterval(self.cadence.poll_ms)
        self.timer.timeout.connect(self.poll)
        self.refresh()

    @Property("QVariantList", notify=changed)
    def sources(self):
        return [dict(label=r["label"]) for r in self.items]

    @Property(str, notify=changed)
    def sourceKind(self):
        return self.kind

    @Property(int, notify=changed)
    def selectedIndex(self):
        return self.selected

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
    def status(self):
        return self.message

    @Property(str, notify=frameChanged)
    def imageUrl(self):
        return (
            f"image://live/{self.session}/{self.version}"
            if not self.provider.image.isNull()
            else ""
        )

    @Property(str, notify=changed)
    def metrics(self):
        if not self.started:
            return "캡처 —   미리보기 —   대기 프레임 0 / 1"
        elapsed = max(0.001, (self.ended or time.perf_counter()) - self.started)
        age = sorted(self.latencies)
        p95 = f"{age[int((len(age) - 1) * 0.95)]:.1f} ms" if age else "—"
        main_count, output_count = self.submitted, self.output_presented
        if self.nativeEnabled:
            counts = self.native.report()
            main_count = counts["main"]["submitted_frames"]
            output_count = counts["output"]["submitted_frames"]
        return (
            f"수신 {self.meta[RECEIVED] / elapsed:.1f} fps  ·  미리보기 제출 {main_count / elapsed:.1f} fps\n"
            f"세션 평균: 처리 {self._stats()[0] / elapsed:.1f} fps · 출력 창 제출 {output_count / elapsed:.1f} fps · 최신 프레임 교체 {self.meta[REPLACED]}\n"
            f"{'Full SBS' if self.sbs else '원본'} {self.meta[WIDTH]} × {self.meta[HEIGHT]}  ·  최근 수신→화면 교환 P95 {p95}\n"
            + (
                f"{self.liveModelLabel} + CUDA · 처리 {self._stats()[0]} · 입력 교체 {self._stats()[1]} · 재초기화 {self._stats()[2]}\n"
                f"최근 전처리/추론/SBS {self._stats()[3] / 1e6:.1f}/{self._stats()[4] / 1e6:.1f}/{self._stats()[5] / 1e6:.1f} ms · CPU 전달 경계 있음"
                if self.sbs
                else f"원본 미리보기 · CPU 복사 경로 · 출력 목표 {self.cadence.hz} fps"
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
        return [
            dict(
                key=key,
                label=f"{profile.resolve().label} · "
                + "/".join(self.desktop.models_label(model) for model in live_model_choices(key)),
            )
            for key, profile in LIVE_MODES.items()
        ]

    @Property("QVariantList", notify=changed)
    def liveModels(self):
        return [
            dict(key=model, label=self.desktop.models_label(model))
            for model in live_model_choices(self.mode)
        ]

    @Property(str, notify=changed)
    def liveModel(self):
        return self.live_model

    @Property(str, notify=changed)
    def liveModelLabel(self):
        return self.desktop.models_label(self.live_model)

    @Property(bool, notify=changed)
    def ovdaConfirmed(self):
        return self.ovda_noncommercial

    @Property(str, notify=changed)
    def liveMode(self):
        return self.mode

    @Property(str, notify=changed)
    def policyDescription(self):
        prefix = (
            "GPU 직접 출력 · 실험 · "
            if self.nativeEnabled
            else "GPU 가속 · 로컬 기본 · "
            if self.gpu_candidate
            else ""
        )
        return (
            prefix
            + LIVE_MODES[self.mode].description
            + " · Offline Quality는 파일 전용"
        )

    @Property(str, notify=changed)
    def supportStatus(self):
        from .live_support import guidance

        if self.sbs and self.gpu_candidate:
            return "RTX 5090 로컬 검증 · 다른 GPU 호환성 별도 · 자동 축소/대체 없음 · 60 fps 보장 아님"

        if not self.sbs:
            return "원본 미리보기 · SBS 성능 수치와 별개입니다."
        if self.active and self.meta[WIDTH]:
            return guidance(self.meta[WIDTH] // 2, self.meta[HEIGHT])
        if 0 <= self.selected < len(self.items):
            source = self.items[self.selected]
            return guidance(source["width"], source["height"])
        return guidance(0, 0)

    @Property(str, notify=changed)
    def processingPath(self):
        if self.native_selected:
            return "gpu-texture"
        return "gpu" if self.gpu_candidate else "reference"

    @Property(bool, notify=changed)
    def nativeEnabled(self):
        return self.sbs and self.native_selected

    @Property(bool, notify=changed)
    def nativeCapable(self):
        return self.sbs and self.live_model == "da2-small"

    @Property(int, notify=changed)
    def nativeSession(self):
        return self.session

    @Property(int, notify=frameChanged)
    def frameRevision(self):
        return self.version

    @Property(bool, notify=frameChanged)
    def hasFrame(self):
        if self.nativeEnabled:
            return self.active and not self.stopping and self.native.has_frame
        return not self.provider.image.isNull()

    @Property(int, notify=changed)
    def presentationHz(self):
        return self.cadence.hz

    @Slot(str)
    def setProcessingPath(self, path):
        if self.active:
            return
        if path not in ("gpu", "reference", "gpu-texture"):
            self.message = "지원하지 않는 처리 경로입니다."
        elif path == "gpu-texture" and self.live_model != "da2-small":
            self.message = "GPU 직접 출력은 현재 Performance · DA2 Small만 지원합니다."
        else:
            try:
                if path == "gpu-texture" and self.native is None:
                    from .native_delivery import NativeDelivery

                    self.native = NativeDelivery()
                self.native_selected = path == "gpu-texture"
                self.gpu_candidate = path != "reference"
            except Exception as error:
                self.message = f"GPU 직접 출력 준비 실패: {error}"
        self.changed.emit()

    @Slot(int)
    def setPresentationHz(self, hz):
        if self.active:
            return
        try:
            self.cadence = PresentationCadence(hz)
            self.timer.setInterval(self.cadence.poll_ms)
        except ValueError as error:
            self.message = str(error)
        self.changed.emit()

    @Slot(str)
    def setMode(self, mode):
        if not self.active:
            if mode not in LIVE_MODES:
                self.message = "지원하지 않는 실시간 모드입니다. Offline Quality는 파일 전용입니다."
            else:
                self.mode = mode
                if self.live_model not in live_model_choices(mode):
                    self.live_model = default_live_model(mode)
                    self.ovda_noncommercial = False
                if self.live_model != "da2-small":
                    self.native_selected = False
            self.changed.emit()

    @Slot(str)
    def setLiveModel(self, model):
        if not self.active and model in live_model_choices(self.mode):
            self.live_model = model
            self.ovda_noncommercial = False
            if model != "da2-small":
                self.native_selected = False
            self.changed.emit()

    @Slot(bool)
    def setOvdaConfirmed(self, confirmed):
        if not self.active and self.live_model == "ovda-small-c16":
            self.ovda_noncommercial = bool(confirmed)
            self.changed.emit()

    @Property("QStringList", notify=changed)
    def outputScreens(self):
        return [screen.name() for screen in QGuiApplication.screens()]

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

    @Slot(int, bool)
    def showOutput(self, index, fullscreen):
        from .capture_sources import exclude_preview

        screens = QGuiApplication.screens()
        if self.output_window is None or not 0 <= index < len(screens):
            return
        window = self.output_window
        window.setScreen(screens[index])
        window.setPosition(screens[index].geometry().topLeft())
        self.output_excluded = exclude_preview(window.winId())
        if not self.output_excluded:
            self.message = (
                "SBS 출력 창의 재캡처 차단에 실패했습니다. 출력 창을 열지 않습니다."
            )
            self.changed.emit()
            return
        window.showFullScreen() if fullscreen else window.showNormal()
        self.output_excluded = exclude_preview(window.winId())
        if not self.output_excluded:
            window.hide()
            self.abort("출력 창 캡처 제외 실패로 중단했습니다.")

    @Slot()
    def outputFrameSwapped(self):
        if (
            self.output_pending is not None
            and self.active
            and not self.stopping
            and self.output_window.isVisible()
        ):
            self.output_presented += 1
            self.output_latencies.append(
                (time.perf_counter_ns() - self.output_pending) / 1e6
            )
            self.output_pending = None

    @Slot()
    def outputVisibilityChanged(self):
        from .capture_sources import exclude_preview

        if self.output_window is not None and self.output_window.isVisible():
            self.output_excluded = exclude_preview(self.output_window.winId())
            if not self.output_excluded:
                self.output_window.hide()
                self.abort("출력 창 캡처 제외 실패로 중단했습니다.")
        else:
            self.output_pending = None

    @Slot()
    def screensChanged(self):
        # Never silently move an active output to a different display.
        if self.output_window is not None and self.output_window.isVisible():
            self.output_window.hide()
            self.abort("디스플레이 구성이 변경되었습니다. 출력 화면을 다시 선택하세요.")
        self.changed.emit()

    @Slot(str)
    def setKind(self, kind):
        if not self.active and kind in ("window", "monitor"):
            self.kind = kind
            self.refresh()

    @Slot(int)
    def select(self, index):
        if not self.active and 0 <= index < len(self.items):
            self.selected = index
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
        try:
            self.items = windows() if self.kind == "window" else monitors()
            self.selected = 0 if self.items else -1
        except Exception as error:
            self.items, self.selected = [], -1
            self.message = str(error)
        self.changed.emit()

    @Slot(bool)
    def setPreviewVisible(self, visible):
        self.preview_visible = visible
        if not visible:
            self.pending_present = None

    @Slot()
    def start(self):
        if self.active or self.desktop.busy:
            return
        try:
            if self.selected < 0:
                raise ValueError("캡처할 대상을 선택하세요.")
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
            if self.nativeEnabled and self.live_model != "da2-small":
                raise ValueError("GPU 직접 출력은 현재 Performance · DA2 Small만 지원합니다.")
            if source["kind"] == "monitor" and not self.excluded:
                raise ValueError(
                    "이 환경에서 미리보기 창의 재캡처를 차단하지 못했습니다. 창 캡처를 사용하세요."
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
            if self.nativeEnabled:
                from .texture_mailbox import TextureMailbox

                self.native.begin(self.session + 1)
                self.texture_mailbox = TextureMailbox.create(context)
            self.mailbox = Mailbox.create(
                context, sbs=self.sbs, metadata_only=self.nativeEnabled
            )
            self.processing_stats = context.RawArray(ctypes.c_longlong, STAT_COUNT)
            from .live_sbs import sbs_worker

            self.process = context.Process(
                target=sbs_worker if self.sbs else capture_worker,
                args=(
                    source,
                    self.cursor,
                    self.mailbox,
                    self.processing_stats,
                    self.strength,
                    self.mode,
                    self.gpu_candidate
                    if self.live_model in (
                        "da2-small",
                        "vda-small",
                        "ovda-small-c16",
                    )
                    else False,
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
                    **({"backend_snapshot": backend_snapshot} if self.sbs else {}),
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
            self.meta = [0] * 12
            self.latencies.clear()
            self.callback_latencies.clear()
            self.pending_present = None
            self.started = time.perf_counter()
            self.cadence.next_ns = 0
            self.ended = None
            self.last_health = self.last_stats = self.started
            self.stopping = False
            self.message = "캡처 시작 중… 화면은 저장되지 않습니다."
            self.timer.start()
        except Exception as error:
            if self.nativeEnabled and self.native is not None:
                self.native.end()
            self.message = str(error)
            if self.desktop.lease.owner == "live":
                self.desktop.lease.release("live")
            self.process = self.mailbox = None
        self.desktop.changed.emit()
        self.changed.emit()

    @Slot()
    def stop(self):
        if self.active and not self.stopping:
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
            self.message = "캡처 종료 중…"
            self.changed.emit()

    def abort(self, message):
        self.stop()
        self.message = str(message)
        self.changed.emit()

    def poll(self):
        if not self.active:
            return
        now = time.perf_counter()
        if not self.process.is_alive():
            if self.nativeEnabled:
                self.native.end()
            # Child has exited: metadata is stable even if a crash held its lock.
            self.meta = list(self.mailbox.meta)
            code = self.process.exitcode
            if not self.stopping:
                error = bytes(self.mailbox.error.value).decode("utf-8", "replace")
                self.message = (
                    error or f"캡처가 중단되었습니다 ({code}). 대상을 다시 선택하세요."
                )
            elif self.message == "캡처 종료 중…":
                self.message = "캡처 종료 · 화면과 임시 프레임을 비웠습니다."
            self.process.join(timeout=0)
            self.process.close()
            self.final_processing_stats = self._stats()
            self.processing_stats = None
            self.process = self.mailbox = None
            self.texture_mailbox = None
            self.provider.image = QImage()
            self.copy_pool.clear()
            self.output_pending = None
            self.ended = now
            self.pending_present = None
            self.timer.stop()
            self.desktop.lease.release("live")
            self.stopping = False
            self.frameChanged.emit()
            self.changed.emit()
            self.desktop.changed.emit()
            if self.desktop.closing:
                self.desktop.exitReady.emit()
            return
        if self.stopping:
            if now - self.stop_started > 5:
                # Only this session's isolated worker. No output files to lose.
                self.process.terminate()
                self.message = "캡처 응답 지연으로 캡처 프로세스를 종료했습니다. 다시 시작할 수 있습니다."
            return
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
                    "캡처 프레임을 받지 못했습니다. 창 상태와 캡처 권한을 확인하세요."
                )
                return
        notify = False
        if self.nativeEnabled:
            try:
                native_changed = self.native.consume(
                    self.texture_mailbox, self.process.pid
                )
                if native_changed and not self.native.has_frame:
                    self.frameChanged.emit()
            except Exception as error:
                self.abort(f"GPU 직접 프레임 전달 실패: {error}")
                return
        if self.cadence.ready(time.perf_counter_ns()) and self.mailbox.lock.acquire(
            False
        ):
            try:
                m = self.mailbox.meta
                self.meta = list(m)
                if m[STATE] == FAILED:
                    error = self.mailbox.error.value.decode("utf-8", "replace")
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
                    self.message = (
                        "● GPU 직접 출력 · 실험 / 녹화 안 함"
                        if self.nativeEnabled
                        else f"● {self.liveModelLabel} 실시간 Full SBS / 녹화 안 함"
                        if self.sbs
                        else "● 캡처 중 · 원본 미리보기 / 녹화 안 함"
                    )
                    if self.notify_unlocked:
                        notify = True
                    else:
                        self.notifyFrame()
            except Exception as failure:
                error = f"화면 프레임 전달 실패: {failure}"
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

    def notifyFrame(self):
        began = time.perf_counter_ns()
        self.frameChanged.emit()
        self.gui_notify_ms = (time.perf_counter_ns() - began) / 1e6
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
        source_device_live = self.live_model in (
            "vda-small",
            "ovda-small-c16",
        ) and self.gpu_candidate
        gpu_live = fused_live or source_device_live
        plan = (
            LIVE_MODES[self.mode].describe(self.strength, self.live_model)
            if self.sbs
            else None
        )
        if plan is not None:
            plan["live"]["presentation_hz"] = self.cadence.hz
        return dict(
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
            native_delivery=self.native.report() if self.nativeEnabled else None,
            frame_swaps=self.presented,
            output_frame_swaps=self.output_presented,
            output_callback_to_swap_ms=list(self.output_latencies),
            processed_frames=self._stats()[0],
            inference_frames=self._stats()[10],
            reused_depth_frames=self._stats()[11],
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
            if gpu_live
            else None,
            host_bridge_timing_scope="input ownership through shared output publication; excludes source wait and Qt",
            host_bridge_ms={
                name: self._stats()[index] / 1e6
                for index, name in enumerate(
                    ("input_copy", "input_color", "output_color", "output_copy"), 20
                )
            },
            gpu_stage_ms={
                name: self._stats()[index] / 1e6
                for index, name in enumerate(
                    (
                        "input_h2d_normalize",
                        "inference_stream_interval",
                        "rgb_h2d_depth_resize",
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
                "capture readback + retained mapped BGRA + RGB/preprocess H2D; GPU SBS surface + per-window GPU copy; 4-byte validity D2H and eligible background depth D2H/H2D"
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
