"""Qt Quick shell. Workers own media/GPU resources; GUI owns only job state."""

from .messages import Message as M, message_value, decode_message
from .localization import localized, render
from .messages import from_payload

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
    Qt,
)
from PySide6.QtGui import QDesktopServices, QSurfaceFormat, QIcon
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow, QSGRendererInterface

from .config import DEFAULT_MODE_MODELS, MODE_MODEL_CHOICES, MODES, OUTPUTS
from .desktop_jobs import (
    BUNDLE,
    PORTABLE_DESKTOP,
    ROOT,
    MODELS,
    VIDEO_SUFFIXES,
    Job,
    ProcessingLease,
    unused_output,
)
from .model_downloads import ModelDownloads
from .desktop_preferences import DesktopPreferences
from .engine_cache import device_identity
from .optional_models import PACKS, available, installed_path, model_root

# pip --target deployments need a retained DLL directory for QML style plugins.
_qt_dll_directory = (
    os.add_dll_directory(str(Path(PySide6.__file__).parent))
    if os.name == "nt"
    else None
)


class DesktopController(QObject):
    changed = Signal()
    exitReady = Signal()

    def __init__(self, preferences=None):
        super().__init__()
        self.preferences = preferences if preferences is not None else DesktopPreferences(portable=PORTABLE_DESKTOP)
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
        self.check_target = ""
        self.status_text = M('Add videos and select one to convert.')
        self.progress_value = 0.0
        self.detail_text = M('Convert to the selected stereo layout · Preserve audio')
        self.setup_text = M('The installation check does not run the model. GPU compatibility and performance need separate validation.')
        self.values = dict(
            model=DEFAULT_MODE_MODELS["performance"],
            mode="performance",
            codec="h264",
            renderer="cuda",
            runtime=str(BUNDLE / "runtime"),
            media=str(BUNDLE / "ffmpeg"),
            engine="",
            noncommercial=False,
            letterbox=False,
            stereo_layout="half-tb",
        )
        self.engine_paths = {
            key: str(ROOT / "out" / info[1]) for key, info in MODELS.items() if info[1]
        }
        for key in self.engine_paths.keys() & PACKS.keys():
            try:
                if model_root(key).is_dir():
                    path = installed_path(key)
                    if available(key, path):
                        self.engine_paths[key] = str(path)
                        continue
                if Path(self.engine_paths[key]).is_dir() and device_identity()['gpu'] != 'NVIDIA GeForce RTX 5090':
                    self.engine_paths[key] = ''
            except (OSError, RuntimeError):
                self.engine_paths[key] = ''
        self.values.update(self.preferences.selection('file', MODES))
        self.values['engine'] = self.engine_paths.get(self.values['model'], '')
        self.downloads = ModelDownloads(self)
        self.active = None

    @Property(QObject, constant=True)
    def modelDownloads(self):
        return self.downloads

    @Property("QVariantMap", notify=changed)
    def missingModels(self):
        return {key: self.downloads.needed(key) for key in PACKS}

    @Property("QVariantList", notify=changed)
    @localized
    def jobs(self):
        labels = dict(queued=M('Queued'), running=M('Converting'), completed=M('Completed'), cancelled=M('Cancelled'), failed=M('Failed'))
        return [dict(row, stateLabel=labels[row["state"]]) for row in self.rows]

    @Property(int, notify=changed)
    def selectedIndex(self):
        return self.selected

    @Property("QVariantMap", notify=changed)
    def settings(self):
        return self.values

    @Property("QVariantList", notify=changed)
    @localized
    def models(self):
        return [
            dict(
                key=key,
                label=(
                    M('VDA Small · 5-frame Offline')
                    if key == "vda-small" and self.values["mode"] == "offline-quality"
                    else MODELS[key][0]
                ),
            )
            for key in MODE_MODEL_CHOICES[self.values["mode"]]
            if not (PORTABLE_DESKTOP and key == "ovda-small-c16")
        ]

    def models_label(self, key):
        return MODELS[key][0]

    @Property('QVariantList', notify=changed)
    @localized
    def depthChoices(self):
        from .model_presentation import selection_choices
        return selection_choices(MODES, self.engine_paths, portable=PORTABLE_DESKTOP)

    @Property(str, notify=changed)
    @localized
    def depthModelHelp(self):
        from .model_presentation import selection_info
        return selection_info(self.values['mode'], self.values['model'], self.engine_paths)['help']

    @Slot(str)
    def selectDepthModel(self, key):
        if self.busy:
            return
        selected = next((entry for entry in self.depthChoices if entry['key'] == key), None)
        if selected is not None:
            self.setOption('mode', selected['mode'])
            self.setOption('model', selected['model'])

    @Property("QVariantList", notify=changed)
    @localized
    def modes(self):
        from .model_presentation import selection_info
        return [dict(key=mode, label=selection_info(mode, DEFAULT_MODE_MODELS[mode], self.engine_paths)['label'])
                for mode in MODES]

    @Property(str, notify=changed)
    @localized
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
    @localized
    def status(self):
        return self.status_text

    @Property(str, notify=changed)
    @localized
    def details(self):
        return self.detail_text

    @Property(str, notify=changed)
    @localized
    def setup(self):
        return self.setup_text

    @Property(float, notify=changed)
    def progress(self):
        return self.progress_value

    @Property(str, notify=changed)
    @localized
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
            and self.rows[self.selected]["state"] == "completed"
            and Path(self.destination).is_file()
        )

    def inform(self, message):
        self.status_text = message_value(message)
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
            "stereo_layout": ("full-sbs", "half-sbs", "full-tb", "half-tb"),
        }
        if name in allowed and value not in allowed[name]:
            return
        if name in ("letterbox", "noncommercial"):
            value = bool(value)
        if name == "mode":
            allowed_models = MODE_MODEL_CHOICES[value]
            if self.values["model"] not in allowed_models:
                model = DEFAULT_MODE_MODELS[value]
                self.values["model"] = model
                self.values["engine"] = self.engine_paths.get(model, "")
                self.values["noncommercial"] = False
        if name == "model":
            if value not in MODE_MODEL_CHOICES[self.values["mode"]]:
                return
            self.values["engine"] = self.engine_paths.get(value, "")
            self.values["noncommercial"] = False
        if name == "engine" and self.values["model"] != "da2-small":
            self.engine_paths[self.values["model"]] = str(value)
        self.values[name] = value
        self.changed.emit()

    @Slot()
    def rememberSelection(self):
        if not self.busy:
            try:
                self.preferences.remember('file', self.values['mode'], self.values['model'], self.values['stereo_layout'])
            except (ValueError, OSError) as error:
                self.inform(error)

    @Slot()
    def chooseFiles(self):
        names, _ = QFileDialog.getOpenFileNames(
            None, render(M('Choose videos to convert')), "", render(M('Videos (*.mp4 *.mkv *.mov *.m4v)'))
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
                    M('The queue holds up to 32 videos. Remove finished items before adding more.')
                )
                break
            if not path.is_file() or path.suffix.lower() not in VIDEO_SUFFIXES:
                continue
            key = str(path.resolve())
            if any(r["source"].casefold() == key.casefold() for r in self.rows):
                continue
            output = unused_output(path, (r["output"] for r in self.rows))
            self.rows.append(
                dict(name=path.name, source=key, output=output, state="queued")
            )
            accepted += 1
        if self.selected == -1 and self.rows:
            self.selected = 0
        if not self.busy:
            self.status_text = (
                M('Added: {v0} · Select a file to convert.', v0=accepted)
                if accepted
                else M('No new supported videos to add.')
            )
        self.changed.emit()

    @Slot(int)
    def select(self, index):
        if not self.busy and 0 <= index < len(self.rows):
            self.selected = index
            self.progress_value = 100 if self.rows[index]["state"] == "completed" else 0
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
            None, render(M('Save SBS video')), self.destination, "MP4 (*.mp4)"
        )
        if value:
            self.rows[self.selected]["output"] = value
            self.rows[self.selected]["state"] = "queued"
            self.changed.emit()

    @Slot(str)
    def chooseDirectory(self, name):
        if not self.busy and name in ("engine", "runtime", "media"):
            value = QFileDialog.getExistingDirectory(
                None, render(M('Choose installation folder')), self.values[name]
            )
            if value:
                self.setOption(name, value)

    def snapshot(self):
        if self.selected < 0:
            raise ValueError(M('Add a video first.'))
        return Job(
            source=self.rows[self.selected]["source"],
            output=self.destination,
            **self.values,
        )

    @Slot()
    def start(self):
        if self.busy:
            return
        if self.downloads.needed(self.values['model']):
            self.showLiveError(M('Install the selected model first. Open the model settings in the file workspace.'))
            return
        try:
            job = self.snapshot()
            job.validate()
            if Path(job.output).exists():
                answer = QMessageBox.question(
                    None,
                    render(M('Replace output file')),
                    render(M('This output file already exists. Replace it after a successful conversion?')),
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
                M('Preparing conversion… Model optimization may take time on first use.')
            )
            self.rows[self.selected]["state"] = "running"
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
            raw = message_value(event.get("message", M('Conversion error')))
            self.error_text = raw if len(raw) <= 2000 else str(raw)[:2000]
            if 'localized' in event:
                try:
                    translated = from_payload(event['localized'])
                    if len(translated) <= 2000:
                        self.error_text = translated
                except (ValueError, TypeError, KeyError, IndexError):
                    pass  # Keep the original bounded diagnostic on malformed metadata.
        elif kind == "complete":
            self.complete = True
        elif kind == "start":
            meta = event.get("metadata", {})
            w, h = meta.get("width"), meta.get("height")
            if type(w) is int and type(h) is int:
                from .stereo_layout import dimensions, LAYOUTS
                layout = self.active.stereo_layout if self.active is not None else self.values["stereo_layout"]
                ow, oh = dimensions(w, h, layout)
                self.detail_text = M('Source {v0} × {v1}  →  {v2} {v3} × {v4}', v0=w, v1=h, v2=LAYOUTS[layout], v3=ow, v4=oh)
        elif kind == "progress" and not self.cancelling:
            self.progress_value = max(0, min(99, float(event.get("percent") or 0)))
            self.status_text = M('Converting · Frame {v0} / {v1}', v0=event.get('frame', 0), v1=event.get('total_frames', '?'))
        elif kind == "offline_depth" and not self.cancelling:
            self.status_text = (
                M('Preparing offline context · Centered {v0}-frame window', v0=event.get('window_frames', '?'))
            )
        elif kind == "engine_build" and not self.cancelling:
            self.status_text = (
                M('Optimizing the model for this GPU. This is only needed on first use.')
            )
        self.changed.emit()

    def _process_error(self, error):
        if error == QProcess.FailedToStart:
            self.error_text = (
                M('Cannot start the processing worker. Check the runtime installation.')
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
                    self.check_target + " · "
                    + (M('Installation verified') if report["ready"] else M('Installation needs attention'))
                    + "\n"
                    + (from_payload(report['localized']) if 'localized' in report else report["message"])
                    + M('\nThis checks installation only; it does not verify engine execution or performance.')
                )
            except (ValueError, KeyError):
                self.setup_text = (
                    self.error_text
                    or M('Installation check failed. Check the paths and Python environment.')
                )
        else:
            success = (
                code == 0
                and exit_status == QProcess.NormalExit
                and self.complete
                and Path(self.active.output).is_file()
            )
            if success:
                state = "completed"
                self.progress_value = 100
                self.status_text = M('Conversion complete · Open the result to review it.')
            elif (
                code == 2 and exit_status == QProcess.NormalExit and not self.error_text
            ):
                state = "cancelled"
                self.status_text = M('Conversion cancelled. The previous output file is preserved.')
            else:
                state = "failed"
                self.status_text = M('Conversion failed · ') + (
                    self.error_text
                    or M('The processing worker exited unexpectedly ({v0}). Check the installation.', v0=code)
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
                    M('Cancellation requested · Waiting for GPU work and file cleanup…')
                )
            except OSError:
                self.inform(
                    M('Cannot record the cancellation request. Check access to the temporary folder.')
                )

    @Slot()
    def checkSetup(self):
        self.checkSetupFor("file")

    @Slot(str)
    def checkSetupFor(self, target):
        if self.busy:
            return
        if target not in ("live", "file"):
            return
        v = dict(self.values)
        if target == "live":
            v["model"] = self.live.liveModel
            v["engine"] = self.engine_paths.get(v["model"], "")
            v["renderer"] = "cuda"
        self.check_target = (M('Live SBS') if target == "live" else M('File conversion')) + " / " + self.models_label(v["model"])
        self.lease.acquire("check")
        self.checking = True
        self.check_buffer = b""
        self.error_text = ""
        self.setup_text = self.check_target + M(' · Checking installation…')
        try:
            self._spawn(
                "depthsbs_app.desktop_check",
                [v[k] for k in ("model", "engine", "runtime", "media", "renderer")],
            )
        except Exception as error:
            self.setup_text = self.check_target + " · " + message_value(error)
            self._cleanup()
        self.changed.emit()

    @Slot()
    def openResult(self):
        if self.canOpen and not QDesktopServices.openUrl(
            QUrl.fromLocalFile(self.destination)
        ):
            self.inform(
                M('Cannot open the default video player. Open the file from its output folder.')
            )

    @Slot()
    def openLicense(self):
        QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(ROOT / "experiments/ovda/LICENSE"))
        )

    @Slot()
    def openResultFolder(self):
        if self.canOpen and not QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(Path(self.destination).parent))
        ):
            self.inform(M('Cannot open the output folder. Check the save location.'))

    @Slot(result=bool)
    def requestClose(self):
        if not self.busy:
            return True
        if self.closing:
            return False
        if self.lease.owner == "live":
            self.closing = True
            self.live.stop()
            return False
        answer = QMessageBox.question(
            None,
            render(M('Exit ScreenTo3D')),
            render(M('Finish cleaning up the current work and exit?')),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self.closing = True
            if self.lease.owner == "model-install":
                self.downloads.cancel()
            elif self.lease.owner == "live":
                self.live.stop()
            elif not self.checking:
                self.cancel()
        return False

    @Slot(QObject, result=bool)
    def protectWindow(self, window):
        from .capture_sources import exclude_preview

        if not exclude_preview(window.winId()):
            window.hide()
            self.live.reportError(M('The utility window was closed because capture protection failed.'))
            return False
        return True

    @Slot(object)
    def showLiveError(self, message):
        if not self.error_dialog.showError(message):
            self.live.stop()
            self.live.stop_message_pending = False
            self.live.message = message_value(message) + M(' · The error window was hidden because capture protection failed.')
            self.live.changed.emit()

    def showModelError(self, message):
        if not self.error_dialog.showError(message, M('Model installation error')):
            self.inform(message)


def create_app(preferences=None):
    if sys.platform == "win32":
        import ctypes
        result = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ScreenTo3D.Desktop")
        if result < 0:
            raise OSError(f"Cannot set ScreenTo3D taskbar identity: {result}")
    # Qt 6.10.2's DXGI VBlank service can stall update delivery on this local
    # display topology. Use Qt's bounded platform timer scheduling, still D3D11.
    # This is explicit, not a software renderer or per-failure fallback.
    os.environ.setdefault("QT_D3D_NO_VBLANK_THREAD", "1")
    # Output pacing is owned by PresentationCadence, not the display refresh.
    # Qt/driver/compositor may still constrain physical presentation.
    os.environ.setdefault("QSG_NO_VSYNC", "1")
    surface = QSurfaceFormat.defaultFormat()
    surface.setSwapInterval(0)
    QSurfaceFormat.setDefaultFormat(surface)
    QQuickWindow.setGraphicsApi(QSGRendererInterface.Direct3D11)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("DepthSBS")
    app.setOrganizationName("DepthSBS")
    # Retain the existing QSettings namespace across the display-name change.
    app.setApplicationDisplayName("ScreenTo3D")
    app.setWindowIcon(QIcon(str(Path(__file__).with_name("assets") / "depthsbs.png")))
    app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    from PySide6.QtQuickControls2 import QQuickStyle

    QQuickStyle.setStyle("Basic")
    controller = DesktopController(preferences)
    from .localization import LanguageManager
    controller.language = LanguageManager(controller.preferences, controller)
    from .live_preview import LivePreview

    controller.live = LivePreview(controller)
    engine = QQmlApplicationEngine()
    engine.setUiLanguage('ko-KR' if controller.language.effectiveLanguage == 'ko' else 'en-US')
    engine.warnings.connect(
        lambda errors: print("\n".join(e.toString() for e in errors), file=sys.stderr)
    )
    engine.rootContext().setContextProperty("desktop", controller)
    engine.rootContext().setContextProperty("live", controller.live)
    engine.rootContext().setContextProperty("i18n", controller.language)
    engine.addImageProvider("live", controller.live.provider)
    engine.addImageProvider("transition", controller.live.transition_provider)
    from .window_icons import WindowIcons
    engine.addImageProvider("windowicons", WindowIcons(controller.live))
    engine.load(QUrl.fromLocalFile(str(Path(__file__).with_name("qml") / "Main.qml")))
    if not engine.rootObjects():
        raise RuntimeError(M('Cannot load the application interface.'))
    window = engine.rootObjects()[0]
    controller.main_window = window
    from .error_dialog import LiveErrorDialog

    controller.error_dialog = LiveErrorDialog(window)
    controller.language.engine = engine
    def refresh_language():
        controller.changed.emit()
        controller.downloads.changed.emit()
        controller.live.changed.emit()
        controller.error_dialog.retranslate()
    controller.language.refresh = refresh_language
    controller.language.errorOccurred.connect(controller.showModelError)
    from .taskbar_identity import attach
    for target in (window, window.findChild(QQuickWindow, "toolsWindow"),
                   window.findChild(QQuickWindow, "sbsOutput"),
                   window.findChild(QQuickWindow, "patternWindow"),
                   controller.error_dialog.windowHandle()):
        attach(target)
    controller.live.errorOccurred.connect(controller.showLiveError)
    controller.live.output_window = window.findChild(QQuickWindow, "sbsOutput")
    controller.live.output_window.setTransientParent(None)
    # Hiding the only output on Stop must retire native scene-graph nodes even
    # when Qt will never render another frame for this window.
    controller.live.output_window.setPersistentSceneGraph(False)
    # Retire graphics with the scene graph. Keeping only graphics persistent
    # can leave Qt's native-texture wrapper without a window RHI on re-exposure.
    controller.live.output_window.setPersistentGraphics(False)
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
    controller.protectWindow(window.findChild(QQuickWindow, "toolsWindow"))
    controller.exitReady.connect(app.quit)
    from .vfg_hotkey import VfgHotkey
    controller.vfg_hotkey = VfgHotkey(app, controller.live)
    window.destroyed.connect(controller.vfg_hotkey.close)
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
