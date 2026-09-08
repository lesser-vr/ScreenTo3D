"""Qt Quick shell. Workers own media/GPU resources; GUI owns only job state."""

import json
import os
import sys
import tempfile
from pathlib import Path

import PySide6

from PySide6.QtCore import (
    QObject,
    Property,
    QProcess,
    QProcessEnvironment,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow, QSGRendererInterface

from .config import MODES, OUTPUTS
from .desktop_jobs import (
    BUNDLE,
    ROOT,
    MODELS,
    VIDEO_SUFFIXES,
    Job,
    ProcessingLease,
    unused_output,
)

# pip --target deployments need a retained DLL directory for QML style plugins.
_qt_dll_directory = (
    os.add_dll_directory(str(Path(PySide6.__file__).parent))
    if os.name == "nt"
    else None
)


class DesktopController(QObject):
    changed = Signal()
    exitReady = Signal()

    def __init__(self):
        super().__init__()
        self.rows = []
        self.selected = -1
        self.lease = ProcessingLease()
        self.process = None
        self.temp = None
        self.cancel_path = None
        self.buffer = b""
        self.check_buffer = b""
        self.error_text = ""
        self.complete = False
        self.cancelling = False
        self.closing = False
        self.checking = False
        self.status_text = "파일을 추가하고 변환할 영상을 선택하세요."
        self.progress_value = 0.0
        self.detail_text = "Full SBS · 원본 크기와 오디오 유지 · 자동 크기 변경 없음"
        self.setup_text = "설치 확인은 모델을 실행하지 않습니다. GPU 호환성과 성능은 별도 검증이 필요합니다."
        self.values = dict(
            model="da2-small",
            mode="balanced",
            codec="h264",
            renderer="cuda",
            runtime=str(BUNDLE / "runtime"),
            media=str(BUNDLE / "ffmpeg"),
            engine="",
            noncommercial=False,
            letterbox=False,
        )
        self.engine_paths = {
            key: str(ROOT / "out" / info[1]) for key, info in MODELS.items() if info[1]
        }
        self.active = None

    @Property("QVariantList", notify=changed)
    def jobs(self):
        return self.rows

    @Property(int, notify=changed)
    def selectedIndex(self):
        return self.selected

    @Property("QVariantMap", notify=changed)
    def settings(self):
        return self.values

    @Property("QVariantList", constant=True)
    def models(self):
        return [dict(key=k, label=v[0]) for k, v in MODELS.items()]

    @Property("QVariantList", constant=True)
    def modes(self):
        return [dict(key=k, label=v.label) for k, v in MODES.items()]

    @Property(str, notify=changed)
    def licenseNotice(self):
        return MODELS[self.values["model"]][3]

    @Property(bool, notify=changed)
    def busy(self):
        return self.lease.owner is not None

    @Property(bool, notify=changed)
    def cancellingNow(self):
        return self.cancelling

    @Property(bool, notify=changed)
    def canCancel(self):
        return self.cancel_path is not None and not self.cancelling

    @Property(str, notify=changed)
    def status(self):
        return self.status_text

    @Property(str, notify=changed)
    def details(self):
        return self.detail_text

    @Property(str, notify=changed)
    def setup(self):
        return self.setup_text

    @Property(float, notify=changed)
    def progress(self):
        return self.progress_value

    @Property(str, notify=changed)
    def destination(self):
        return (
            self.rows[self.selected]["output"]
            if 0 <= self.selected < len(self.rows)
            else ""
        )

    @Property(bool, notify=changed)
    def canOpen(self):
        return (
            0 <= self.selected < len(self.rows)
            and self.rows[self.selected]["state"] == "완료"
            and Path(self.destination).is_file()
        )

    def inform(self, message):
        self.status_text = str(message)
        self.changed.emit()

    @Slot(str, "QVariant")
    def setOption(self, name, value):
        if self.busy or name not in self.values:
            return
        allowed = {
            "model": MODELS,
            "mode": MODES,
            "codec": OUTPUTS,
            "renderer": ("cpu", "cuda"),
        }
        if name in allowed and value not in allowed[name]:
            return
        if name in ("letterbox", "noncommercial"):
            value = bool(value)
        if name == "model":
            self.values["engine"] = self.engine_paths.get(value, "")
            self.values["noncommercial"] = False
        if name == "engine" and self.values["model"] != "da2-small":
            self.engine_paths[self.values["model"]] = str(value)
        self.values[name] = value
        self.changed.emit()

    @Slot()
    def chooseFiles(self):
        names, _ = QFileDialog.getOpenFileNames(
            None, "변환할 영상 선택", "", "영상 (*.mp4 *.mkv *.mov *.m4v)"
        )
        self.add_paths(names)

    @Slot("QVariantList")
    def dropFiles(self, urls):
        self.add_paths([QUrl(u).toLocalFile() for u in urls if QUrl(u).isLocalFile()])

    def add_paths(self, names):
        accepted = 0
        for name in names:
            path = Path(name)
            if len(self.rows) >= 32:
                self.inform(
                    "목록은 최대 32개입니다. 완료한 항목을 제거한 뒤 추가하세요."
                )
                break
            if not path.is_file() or path.suffix.lower() not in VIDEO_SUFFIXES:
                continue
            key = str(path.resolve())
            if any(r["source"].casefold() == key.casefold() for r in self.rows):
                continue
            output = unused_output(path, (r["output"] for r in self.rows))
            self.rows.append(
                dict(name=path.name, source=key, output=output, state="대기")
            )
            accepted += 1
        if self.selected == -1 and self.rows:
            self.selected = 0
        if not self.busy:
            self.status_text = (
                f"{accepted}개 추가됨 · 선택한 파일을 변환하세요."
                if accepted
                else "새로 추가할 지원 영상이 없습니다."
            )
        self.changed.emit()

    @Slot(int)
    def select(self, index):
        if not self.busy and 0 <= index < len(self.rows):
            self.selected = index
            self.progress_value = 100 if self.rows[index]["state"] == "완료" else 0
            self.status_text = (
                self.rows[index]["state"] + " · " + self.rows[index]["name"]
            )
            self.changed.emit()

    @Slot()
    def removeSelected(self):
        if not self.busy and 0 <= self.selected < len(self.rows):
            self.rows.pop(self.selected)
            self.selected = min(self.selected, len(self.rows) - 1)
            self.changed.emit()

    @Slot()
    def chooseOutput(self):
        if self.busy or self.selected < 0:
            return
        value, _ = QFileDialog.getSaveFileName(
            None, "SBS 저장 위치", self.destination, "MP4 (*.mp4)"
        )
        if value:
            self.rows[self.selected]["output"] = value
            self.rows[self.selected]["state"] = "대기"
            self.changed.emit()

    @Slot(str)
    def chooseDirectory(self, name):
        if not self.busy and name in ("engine", "runtime", "media"):
            value = QFileDialog.getExistingDirectory(
                None, "설치 폴더 선택", self.values[name]
            )
            if value:
                self.setOption(name, value)

    def snapshot(self):
        if self.selected < 0:
            raise ValueError("먼저 영상을 추가하세요.")
        return Job(
            source=self.rows[self.selected]["source"],
            output=self.destination,
            **self.values,
        )

    @Slot()
    def start(self):
        if self.busy:
            return
        try:
            job = self.snapshot()
            job.validate()
            if Path(job.output).exists():
                answer = QMessageBox.question(
                    None,
                    "출력 파일 교체",
                    "이미 존재하는 출력 파일입니다. 변환 성공 시 교체할까요?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if answer != QMessageBox.Yes:
                    return
            self.launch(job)
        except Exception as error:
            self.inform(error)

    def launch(self, job):
        job.validate()
        self.lease.acquire("file")
        try:
            self.temp = tempfile.TemporaryDirectory(prefix="depthsbs-desktop-")
            self.cancel_path = Path(self.temp.name) / "cancel"
            self.active = job
            self.complete = self.cancelling = False
            self.error_text = ""
            self.buffer = b""
            self.progress_value = 0
            self.status_text = (
                "변환 준비 중… 첫 실행은 모델 최적화에 시간이 걸릴 수 있습니다."
            )
            self.rows[self.selected]["state"] = "변환 중"
            self._spawn("depthsbs_app.desktop_worker", job.arguments(self.cancel_path))
        except Exception:
            self._cleanup()
            raise
        self.changed.emit()

    def _spawn(self, module, arguments):
        process = QProcess(self)
        self.process = process
        executable = Path(sys.executable)
        # pythonw has no Python stdout, even with inherited pipes. Workers need
        # python.exe for the JSON event protocol; QProcess does not show a console.
        if executable.name.lower() == "pythonw.exe":
            executable = executable.with_name("python.exe")
        process.setProgram(str(executable))
        process.setArguments(["-u", "-m", module, *arguments])
        process.setWorkingDirectory(str(ROOT))
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONIOENCODING", "utf-8")
        process.setProcessEnvironment(env)
        process.readyReadStandardOutput.connect(self._read)
        # Drain stderr without storing private paths or unlimited native logs.
        process.readyReadStandardError.connect(lambda: process.readAllStandardError())
        process.finished.connect(self._finished)
        process.errorOccurred.connect(self._process_error)
        process.start()

    def _read(self):
        if self.process is None:
            return
        data = bytes(self.process.readAllStandardOutput())
        if self.checking:
            self.check_buffer = (self.check_buffer + data)[-262144:]
            return
        self.buffer += data
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            if len(line) > 262144:
                continue
            try:
                event = json.loads(line)
                if isinstance(event, dict):
                    self._event(event)
            except (ValueError, TypeError, KeyError):
                continue
        if len(self.buffer) > 262144:
            self.buffer = b""

    def _event(self, event):
        kind = event.get("event")
        if kind == "error":
            self.error_text = str(event.get("message", "변환 오류"))[:2000]
        elif kind == "complete":
            self.complete = True
        elif kind == "start":
            meta = event.get("metadata", {})
            w, h = meta.get("width"), meta.get("height")
            if type(w) is int and type(h) is int:
                self.detail_text = f"원본 / 각 눈 {w} × {h}  →  Full SBS {w * 2} × {h}"
        elif kind == "progress" and not self.cancelling:
            self.progress_value = max(0, min(99, float(event.get("percent") or 0)))
            self.status_text = f"변환 중 · {event.get('frame', 0)} / {event.get('total_frames', '?')} 프레임"
        elif kind == "engine_build" and not self.cancelling:
            self.status_text = (
                "이 GPU에 맞게 모델을 최적화하고 있습니다. 첫 실행에만 필요합니다."
            )
        self.changed.emit()

    def _process_error(self, error):
        if error == QProcess.FailedToStart:
            self.error_text = (
                "처리 프로그램을 시작할 수 없습니다. 실행 환경을 확인하세요."
            )
            self._finished(1, QProcess.CrashExit)

    def _finished(self, code, exit_status):
        if self.process is None:
            return
        self._read()
        if self.checking:
            try:
                report = json.loads(self.check_buffer)
                self.setup_text = (
                    ("설치 항목 확인됨" if report["ready"] else "설치 확인 필요")
                    + "\n"
                    + report["message"]
                    + "\n엔진 실행·성능 보증이 아닌 설치 점검 결과입니다."
                )
            except (ValueError, KeyError):
                self.setup_text = (
                    self.error_text
                    or "설치 확인에 실패했습니다. 경로와 Python 환경을 확인하세요."
                )
        else:
            success = (
                code == 0
                and exit_status == QProcess.NormalExit
                and self.complete
                and Path(self.active.output).is_file()
            )
            if success:
                state = "완료"
                self.progress_value = 100
                self.status_text = "변환 완료 · 결과 영상을 열어 확인하세요."
            elif (
                code == 2 and exit_status == QProcess.NormalExit and not self.error_text
            ):
                state = "취소됨"
                self.status_text = "변환을 취소했습니다. 기존 출력 파일은 유지됩니다."
            else:
                state = "오류"
                self.status_text = "변환 실패 · " + (
                    self.error_text
                    or f"처리 프로그램이 비정상 종료되었습니다 ({code}). 설치 환경을 확인하세요."
                )
            self.rows[self.selected]["state"] = state
        self._cleanup()
        self.changed.emit()
        if self.closing:
            self.exitReady.emit()

    def _cleanup(self):
        if self.process is not None:
            self.process.deleteLater()
        self.process = None
        if self.temp is not None:
            self.temp.cleanup()
        self.temp = self.cancel_path = None
        owner = self.lease.owner
        if owner is not None:
            self.lease.release(owner)
        self.checking = self.cancelling = False

    @Slot()
    def cancel(self):
        if self.cancel_path is not None:
            try:
                self.cancel_path.write_text("cancel", encoding="ascii")
                self.cancelling = True
                self.inform(
                    "취소 요청됨 · GPU 작업과 파일 정리가 끝날 때까지 기다리는 중…"
                )
            except OSError:
                self.inform(
                    "취소 요청을 기록하지 못했습니다. 임시 폴더 접근 권한을 확인하세요."
                )

    @Slot()
    def checkSetup(self):
        if self.busy:
            return
        self.lease.acquire("check")
        self.checking = True
        self.check_buffer = b""
        self.error_text = ""
        self.setup_text = "설치 항목을 확인하고 있습니다…"
        v = self.values
        try:
            self._spawn(
                "depthsbs_app.desktop_check",
                [v[k] for k in ("model", "engine", "runtime", "media", "renderer")],
            )
        except Exception as error:
            self.setup_text = str(error)
            self._cleanup()
        self.changed.emit()

    @Slot()
    def openResult(self):
        if self.canOpen and not QDesktopServices.openUrl(
            QUrl.fromLocalFile(self.destination)
        ):
            self.inform(
                "기본 영상 플레이어를 열 수 없습니다. 저장 위치에서 파일을 확인하세요."
            )

    @Slot()
    def openLicense(self):
        QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(ROOT / "experiments/ovda/LICENSE"))
        )

    @Slot(result=bool)
    def requestClose(self):
        if not self.busy:
            return True
        if self.closing:
            return False
        answer = QMessageBox.question(
            None,
            "작업 종료",
            "진행 중인 작업을 정리한 뒤 앱을 종료할까요?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self.closing = True
            if self.lease.owner == "live":
                self.live.stop()
            elif not self.checking:
                self.cancel()
        return False


def create_app():
    # Qt 6.10.2's DXGI VBlank service can stall update delivery on this local
    # display topology. Use Qt's bounded platform timer scheduling, still D3D11.
    # This is explicit, not a software renderer or per-failure fallback.
    os.environ.setdefault("QT_D3D_NO_VBLANK_THREAD", "1")
    QQuickWindow.setGraphicsApi(QSGRendererInterface.Direct3D11)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("DepthSBS")
    app.setOrganizationName("DepthSBS")
    from PySide6.QtQuickControls2 import QQuickStyle

    QQuickStyle.setStyle("Basic")
    controller = DesktopController()
    from .live_preview import LivePreview

    controller.live = LivePreview(controller)
    engine = QQmlApplicationEngine()
    engine.warnings.connect(
        lambda errors: print("\n".join(e.toString() for e in errors), file=sys.stderr)
    )
    engine.rootContext().setContextProperty("desktop", controller)
    engine.rootContext().setContextProperty("live", controller.live)
    engine.addImageProvider("live", controller.live.provider)
    engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("qml") / "Main.qml")))
    if not engine.rootObjects():
        raise RuntimeError("GUI 화면을 불러오지 못했습니다.")
    window = engine.rootObjects()[0]
    controller.main_window = window
    controller.live.output_window = window.findChild(QQuickWindow, "sbsOutput")
    controller.live.output_window.frameSwapped.connect(
        controller.live.outputFrameSwapped
    )
    controller.live.output_window.visibilityChanged.connect(
        controller.live.outputVisibilityChanged
    )
    app.screenAdded.connect(controller.live.screensChanged)
    app.screenRemoved.connect(controller.live.screensChanged)
    window.frameSwapped.connect(controller.live.frameSwapped)
    controller.live.frameChanged.connect(window.update)
    controller.live.frameChanged.connect(controller.live.output_window.update)
    from .capture_sources import exclude_preview

    controller.live.excluded = exclude_preview(window.winId())
    controller.exitReady.connect(app.quit)
    return app, engine, controller


def main():
    app, engine, controller = create_app()
    try:
        return app.exec()
    finally:
        # QML bindings must be destroyed before their Python context object.
        import shiboken6

        shiboken6.delete(engine)


if __name__ == "__main__":
    sys.exit(main())
