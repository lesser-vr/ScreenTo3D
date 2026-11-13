"""User-selected-window A/B launcher; never imported by normal application startup."""
import argparse
from collections import deque
from datetime import datetime
import json
import os
from pathlib import Path
from statistics import median
import sys
import time
from unittest.mock import patch

from PySide6.QtCore import QObject, QTimer, Qt, Slot

from screento3d_app.desktop_jobs import ROOT
from owl_output import OwlOutputLive
from screento3d_app.output_placement import OutputPlacement
from native_path import install


def comparison_mode(model, enabled):
    if model == 'da2-small':
        return 'performance'
    if model == 'da2-base':
        return 'balanced'
    raise ValueError('이 비교 실행은 DA2 Small 또는 Base를 지원합니다.')


class ComparisonLive(OwlOutputLive):
    """Keep unsupported comparison settings from starting capture or a GPU worker."""
    vfg_configurable = False  # Dedicated A/B launchers retain their fixed experiment mode.
    observer = None
    comparison_model = 'da2-base'

    @Slot()
    def start(self):
        if self.active or self.desktop.busy:
            return
        expected = 'performance' if self.comparison_model == 'da2-small' else 'balanced'
        if self.mode != expected or self.live_model != self.comparison_model:
            label = 'Small' if expected == 'performance' else 'Base'
            self.reportError(f"이 비교 실행은 DA2 {label} 전용입니다. 깊이 모델에서 DA2 {label}을 선택하세요.")
            return
        if not self.sbs or not self.gpu_candidate or not self.native_selected:
            self.reportError("이 비교 실행은 GPU 직접 출력 전용입니다. 설정과 진단에서 GPU 직접 출력을 선택하세요.")
            return
        if self.kind != "window":
            self.reportError("이 비교 실행은 창 캡처 전용입니다. 메뉴에서 ‘창 선택으로 전환’을 선택하세요.")
            return
        if self.observer is not None and self.observer.record is not None:
            self.observer.finish()
        super().start()
        if self.active and self.observer is not None:
            self.observer.begin()


def summarize(samples, began, ended, base_frames):
    """Bounded observer samples; ages are capture-to-Qt, not physical latency."""
    seconds = (ended - began) / 1e9
    current = [s for s in samples if began < s[0] <= ended]
    originals = [s for s in current if s[5] == 0]
    generated = [s for s in current if s[5] == 1]

    def age(rows, column):
        return median((s[0] - s[column]) / 1e6 for s in rows) if rows else None

    return dict(seconds=seconds, output_fps=len(current) / seconds,
                original_fps=len(originals) / seconds, generated_fps=len(generated) / seconds,
                base_fps=base_frames / seconds, observed_frames=len(current),
                original_age_p50_ms=age(originals, 3), generated_midpoint_age_p50_ms=age(generated, 3),
                generated_oldest_age_p50_ms=age(generated, 4))


from screento3d_app.environment import get as app_env

class ComparisonObserver(QObject):
    def __init__(self, desktop, output, enabled):
        super().__init__(desktop)
        self.desktop, self.live, self.output = desktop, desktop.live, output
        model_label = 'Small' if self.live.comparison_model == 'da2-small' else 'Base'
        self.label = f"{'B' if enabled else 'A'} · DA2 {model_label}" + (' · VFG' if enabled else '')
        self.enabled = enabled
        self.samples = deque(maxlen=8192)
        self.rows = deque(maxlen=60)
        self.record = None
        self.connected = False
        self.last_seen = 0
        self.error_seen = False
        self.write_failed = False
        self.live.observer = self
        self.live.errorOccurred.connect(self.on_error)
        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.set_title("볼 창을 선택하세요")

    def on_error(self, _message):
        self.error_seen = True

    def set_title(self, detail):
        self.desktop.main_window.setTitle(f"ScreenTo3D · {self.label} · {detail}")
        self.live.output_window.setTitle(f"ScreenTo3D · {self.label} · {detail} · F11 전체 화면")

    def begin(self):
        from screento3d_app.live_sbs import DEFAULT_STEREO_QUALITY
        if self.record is not None:
            self.finish()
        live = self.live
        self.samples.clear()
        self.rows.clear()
        self.last_seen = 0
        self.error_seen = False
        self.record = dict(session=live.session, variant="vfg" if self.enabled else "baseline",
                           output_capture="allowed-for-external-display",
                           model=live.live_model, strength=live.strength, output_cap=live.cadence.hz,
                           stereo_quality=app_env('SCREENTO3D_STEREO_QUALITY',DEFAULT_STEREO_QUALITY),
                           cursor=live.cursor, state="preparing", rows=[],
                           scope="Recent Qt completion windows after observer attachment; not physical scanout; no frames or source identities saved")
        live.native.visible = lambda: live.output_window.isVisible()
        live.native.on_published = self.notify_frame
        self.set_title("SBS 준비 중")
        self.save()

    def notify_frame(self):
        self.live.version += 1
        self.live.notifyFrame()

    def on_frame(self):
        # Direct render-thread callback, attached after native metrics are active.
        native = self.live.native
        sequence = native.report()["output"]["last_submitted_id"]
        if sequence and sequence != self.last_seen:
            self.last_seen = sequence
            timing = native.records.get(sequence)
            if timing is not None:
                self.samples.append((time.perf_counter_ns(), *timing))

    def tick(self):
        if self.record is None:
            return
        if not self.live.active:
            self.finish()
            return
        if not self.connected:
            if not self.live.native.report()["output"]["submitted_frames"]:
                return
            self.live.output_window.afterFrameEnd.connect(self.on_frame, Qt.DirectConnection)
            self.connected = True
            self.began = time.perf_counter_ns()
            self.base_before = self.live._stats()[0]
            self.record["state"] = "running"
        ended = time.perf_counter_ns()
        if ended - self.began < 2_000_000_000:
            return
        base = self.live._stats()[0]
        row = summarize(tuple(self.samples), self.began, ended, base - self.base_before)
        row["output_visible"] = self.live.output_window.isVisible()
        self.rows.append(row)
        self.began, self.base_before = ended, base
        age = row["original_age_p50_ms"]
        detail = f"출력 {row['output_fps']:.0f} · 원본 {row['original_fps']:.0f} · 보간 {row['generated_fps']:.0f} fps"
        if age is not None:
            detail += f" · 지연 {age:.0f}ms"
        if not row["output_visible"]:
            detail = "출력 창 숨김 · 측정 제외"
        self.set_title(detail)
        self.record["sbs_size"] = list(self.live.meta[2:4])
        self.save()

    def save(self):
        if self.record is None or self.write_failed:
            return
        self.record["rows"] = list(self.rows)
        self.record["error_seen"] = self.error_seen
        path = self.output / f"session-{self.record['session']}.json"
        try:
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.record, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(path)
        except OSError:
            self.write_failed = True
            self.live.reportError("비교 수치를 저장하지 못했습니다. 디스크 공간과 결과 폴더 권한을 확인하세요.")

    def finish(self):
        if self.connected:
            self.live.output_window.afterFrameEnd.disconnect(self.on_frame)
            self.connected = False
        if self.record is not None:
            self.record["state"] = "ended_with_error" if self.error_seen else "stopped"
            report = self.live.native.report()
            self.record["cleanup"] = dict(live_pools=report["live_pools"], live_nodes=report["live_nodes"],
                                           has_frame=self.live.hasFrame)
            self.save()
            self.record = None
        self.set_title("중지됨 · 볼 창을 선택하세요")


def create_comparison(output: Path, enabled: bool, model: str = 'da2-base'):
    """One mode per process; capture remains explicit through the ordinary UI."""
    mode = comparison_mode(model, enabled)
    os.environ["SCREENTO3D_VFG_EVIDENCE"] = str(output)
    os.environ["SCREENTO3D_VFG_TEST_CUT_EVERY"] = "0"
    os.environ["SCREENTO3D_STEREO_RENDERER"] = "cuda"
    os.environ["SCREENTO3D_LIVE_GPU_CANDIDATE"] = "1"
    os.environ["SCREENTO3D_CAPTURE_TELEMETRY"] = "0"
    install(enabled)
    from screento3d_app import desktop, live_preview
    with patch.object(live_preview, "LivePreview", ComparisonLive):
        app, engine, controller = desktop.create_app()
    controller.live.comparison_model = model
    controller.live.setMode(mode)
    # Owl3D's source discovery must see the SBS HWND as its own root window,
    # rather than resolve its fullscreen surface to the small control window.
    # QObject ownership and the existing close/stop handler remain unchanged.
    controller.live.output_window.setTransientParent(None)
    # A shared comparison-only placement preserves A/B output geometry without
    # overwriting the normal app's preference or storing source selection.
    controller.live.output_placement = OutputPlacement(ROOT / "out/vfg-comparison-placement.json")
    observer = ComparisonObserver(controller, output, enabled)
    return app, engine, controller, observer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vfg", action="store_true")
    parser.add_argument("--model", choices=('da2-base','da2-small'), default='da2-base')
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        comparison_mode(args.model, args.vfg)
    except ValueError as error:
        parser.error(str(error))
    output = args.output or ROOT / "out/vfg-comparison" / (
        datetime.now().strftime("%Y%m%d-%H%M%S-%f") +
        ("-B-small-vfg" if args.vfg and args.model == 'da2-small' else "-B-vfg" if args.vfg else "-A-small" if args.model == 'da2-small' else "-A-baseline"))
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    app, engine, controller, observer = create_comparison(output, args.vfg, args.model)
    try:
        return app.exec()
    finally:
        observer.timer.stop()
        observer.finish()
        import shiboken6
        shiboken6.delete(engine)


if __name__ == "__main__":
    sys.exit(main())
