"""Qt adapter for an explicitly requested optional model installation."""
from .messages import ErrorMessage as E

from .messages import Message as M, message_value, decode_message, as_error
from .localization import localized, render
import threading
import time
import http.client
from pathlib import Path
from urllib.error import HTTPError, URLError

from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer, QStandardPaths, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog

from .engine_cache import require_runtime_device
from .optional_models import PACKS, available, install, installed_path, source_for
from .vfg_runtime import BRIDGE, runtime_path


class ModelDownloads(QObject):
    changed = Signal()
    updateProgress = Signal(object, int)
    finished = Signal(str, object, bool)

    def __init__(self, desktop):
        super().__init__(desktop)
        self.desktop = desktop
        self.active_key = ''
        self.last_key = ''
        self.message = ''
        self.percent = -1
        self.stop_event = threading.Event()
        self.setup_visible=False
        self.setup_key=''
        self.sequence=[]
        self.resume=None
        self.waiting_key=''
        self.handoff=None
        self.download_timer=QTimer(self)
        self.download_timer.setInterval(1000)
        self.download_timer.timeout.connect(self._downloadReady)
        self.updateProgress.connect(self._progress)
        self.finished.connect(self._finished)

    @Property(bool,notify=changed)
    def setupVisible(self):return self.setup_visible

    @Property(str,notify=changed)
    def setupKey(self):return self.setup_key

    @Property(bool,notify=changed)
    def willResume(self):return self.resume is not None

    @Property(str,notify=changed)
    def waitingKey(self):return self.waiting_key

    def ensure(self,keys,resume):
        """An explicit Start/Install action authorizes this ordered setup only."""
        missing=[key for key in dict.fromkeys(keys) if key and self.needed(key)]
        if not missing:return True
        if self.desktop.busy:return False
        if self.setup_visible and self.sequence:return False
        self.sequence=missing;self.resume=resume;self.setup_visible=True
        self._advance()
        return False

    def _advance(self):
        while self.sequence and not self.needed(self.sequence[0]):self.sequence.pop(0)
        if self.sequence:
            key=self.sequence[0]
            self.setup_key=key;self.changed.emit()
            # Showing the protected window can synchronously dismiss setup.
            if self.setup_visible and self.sequence and self.setup_key==key:
                self.begin(key,False)
        else:
            resume=self.resume;self.resume=None;self.setup_visible=False;self.setup_key=''
            self.changed.emit()
            if resume is not None and not self.desktop.closing:resume()

    @Slot()
    def dismissSetup(self):
        self.sequence=[];self.resume=None;self.setup_visible=False
        if self.active_key or self.waiting_key:self.cancel()
        self.changed.emit()

    @Property(str, notify=changed)
    @localized
    def activeKey(self):
        return self.active_key

    @Property(str, notify=changed)
    @localized
    def lastKey(self):
        return self.last_key

    @Property(str, notify=changed)
    @localized
    def status(self):
        return self.message

    @Property(int, notify=changed)
    def percentage(self):
        return self.percent

    @Slot(str, result=bool)
    def needed(self, key):
        from .desktop_runtimes import PACKS as components,deferred
        if key in components:
            from .desktop_jobs import BUNDLE
            directory=BUNDLE/('runtime' if key=='trt-core' else 'ffmpeg')
            return deferred(directory,key) and not available(key,installed_path(key))
        from .builder_resources import PACKS as resources,ready
        if key in resources:
            return key==self.desktop.gpuRuntimeKey and not ready(key)
        return key in PACKS and not available(key, runtime_path() if key == 'vfg'
                                               else self.desktop.engine_paths.get(key))

    @Slot(str, result=str)
    @localized
    def description(self, key):
        if key not in PACKS:
            return ''
        pack = PACKS[key]
        from .official_sources import OfficialSource
        try:source=source_for(key)
        except (FileNotFoundError,ValueError):source=None
        if isinstance(source,OfficialSource):
            if source.cached:
                return M('{name}\nDownloaded files will be verified and reused.\n{terms}',name=pack.name,terms=render(pack.terms))
            return M('{name} · up to {size:.0f} MB\n{terms}\nPreviously downloaded files are reused.',name=pack.name,size=source.size/1e6,terms=render(pack.terms))
        return M('{name} · {size:.0f} MB\n{terms}', name=pack.name, size=pack.size / 1e6, terms=render(pack.terms))

    @Slot(str, result=str)
    @localized
    def installAction(self, key):
        if key not in PACKS:
            return ''
        try:
            source = source_for(key)
        except FileNotFoundError:
            return M('Download in browser')
        except ValueError:
            return M('Download and install')
        return M('Install local pack') if isinstance(source, Path) else M('Download and install')

    @Slot(str,result=str)
    @localized
    def downloadHelp(self,key):
        if key not in PACKS:return ''
        try:source_for(key)
        except FileNotFoundError:
            return M('Download {filename} in your browser. Sign in to GitHub if asked. Save it to Downloads; installation continues automatically. For another folder, use Install from file.',filename=PACKS[key].filename)
        except ValueError:return ''  # A malformed configured origin remains an error.
        return ''

    def _prepare_gpu_install(self, key, resume):
        from .builder_resources import PACKS as resources, required_key
        from .optional_models import GRAPH_HASHES

        if key != 'trt-core' and key not in resources and key not in GRAPH_HASHES:
            return True
        try:
            device = require_runtime_device()
        except RuntimeError as error:
            self.dismissSetup()
            self.desktop.showModelError(error)
            return False
        if key in GRAPH_HASHES:
            return self.ensure(['trt-core', required_key(device=device)], resume)
        return True

    @Slot(str)
    def downloadInBrowser(self,key):
        if self.desktop.busy or self.waiting_key or key not in PACKS or not self.needed(key):return
        if self.setup_visible and self.setup_key!=key:return
        if not self._prepare_gpu_install(key, lambda: self.downloadInBrowser(key)):
            return
        from .browser_download import DownloadHandoff,release_url
        directory=QStandardPaths.writableLocation(QStandardPaths.DownloadLocation)
        if not directory:
            self.message=M('Choose the downloaded file with Install from file.')
            self.last_key=key;self.changed.emit();return
        pack=PACKS[key]
        handoff=DownloadHandoff(directory,pack.filename,pack.size,time.monotonic())
        if not QDesktopServices.openUrl(QUrl(release_url(pack.filename))):
            self.sequence=[];self.resume=None;self.changed.emit()
            self.desktop.showModelError(E('E_DOWNLOAD_BROWSER'));return
        if not self.setup_visible:self.setup_key=key;self.setup_visible=True
        self.waiting_key=key;self.handoff=handoff
        self.last_key=key;self.percent=-1
        self.message=M('Waiting for the download to finish. Keep this window open.')
        self.download_timer.start();self.changed.emit()

    def _stopWaiting(self):
        self.download_timer.stop();self.waiting_key='';self.handoff=None

    def _downloadReady(self):
        if not self.handoff:return
        if self.desktop.closing:
            self.dismissSetup();return
        try:path=self.handoff.ready(time.monotonic())
        except TimeoutError:
            self._stopWaiting();self.sequence=[];self.resume=None
            self.message=M('Download not detected. Use Install from file to choose it, then start your task again.')
            self.changed.emit();return
        if path is not None and not self.desktop.busy:
            key=self.waiting_key;self._stopWaiting()
            self._install(key,path)

    @Slot(str, bool)
    def begin(self, key, choose_file):
        if key not in PACKS or self.desktop.busy or not self.needed(key):
            return
        if self.setup_visible and self.setup_key!=key:return
        if self.waiting_key and self.waiting_key!=key:return
        if not self._prepare_gpu_install(key, lambda: self.begin(key, choose_file)):
            return
        if key == 'vfg' and not BRIDGE.is_file():
            self.desktop.showModelError(E('E_VFG_MODULE_MISSING'))
            return
        try:
            if choose_file:
                filename, _ = QFileDialog.getOpenFileName(None, render(M('Choose a model installation file')), '',
                                                          render(M('Installation file ({v0})', v0=PACKS[key].filename)))
                if not filename:
                    return
                source = Path(filename)
            else:
                try:source = source_for(key)
                except FileNotFoundError:
                    # Missing distribution configuration is an onboarding state.
                    # The action remains available through the user's browser.
                    if not self.setup_visible:
                        self.setup_key=key;self.setup_visible=True
                    self.changed.emit();return
        except Exception as exc:
            self.sequence=[];self.resume=None;self.changed.emit()
            self.desktop.showModelError(exc)
            return
        self._stopWaiting()
        self._install(key,source)

    def _install(self,key,source):
        self.desktop.lease.acquire('model-install')
        self.active_key, self.message, self.percent = key, M('Connecting…'), -1
        self.last_key = key
        self.stop_event.clear()
        self.changed.emit()
        self.desktop.changed.emit()

        def work():
            last = None

            def progress(stage, pct):
                nonlocal last
                if (stage, pct) != last:
                    self.updateProgress.emit(stage, pct)
                    last = stage, pct

            try:
                install(key, source, installed_path(key), progress, self.stop_event.is_set)
            except InterruptedError:
                self.finished.emit(key, E('E_INSTALL_CANCELLED'), False)
            except (HTTPError, URLError, TimeoutError,ConnectionError,http.client.IncompleteRead) as exc:
                self.finished.emit(key, E('E_MODEL_CONNECTION', v0=exc), True)
            except Exception as exc:
                self.finished.emit(key, as_error(exc), True)
            else:
                self.finished.emit(key, '', False)
        threading.Thread(target=work, name='ScreenTo3D model install', daemon=True).start()

    @Slot()
    def cancel(self):
        self.sequence=[];self.resume=None
        if self.waiting_key:
            self._stopWaiting()
            self.message=M('Setup cancelled. A browser download may still finish.')
            self.changed.emit();return
        self.stop_event.set()
        self.message = M('Cancelling installation…')
        self.changed.emit()

    @Slot(object, int)
    def _progress(self, message, percent):
        if not self.stop_event.is_set():
            self.message, self.percent = message, percent
            self.changed.emit()

    @Slot(str, object, bool)
    def _finished(self, key, message, failed):
        from .optional_models import GRAPH_HASHES
        if not message and key in GRAPH_HASHES:
            path = str(installed_path(key))
            self.desktop.engine_paths[key] = path
            if self.desktop.values['model'] == key:
                self.desktop.values['engine'] = path
        self.active_key = ''
        self.message = message or M('{v0} installed', v0=PACKS[key].name)
        self.desktop.lease.release('model-install')
        self.changed.emit()
        self.desktop.changed.emit()
        live = getattr(self.desktop, 'live', None)
        if live is not None:
            live.changed.emit()
        if self.desktop.closing:
            self.desktop.exitReady.emit()
        elif failed:
            self.desktop.showModelError(message)
            # Retry from Start or the explicit installer; failure never auto-starts.
            self.sequence=[];self.resume=None
            self.changed.emit()
        elif message:
            self.sequence=[];self.resume=None;self.setup_visible=False;self.changed.emit()
        elif self.sequence:
            self._advance()
        elif self.setup_visible and key==self.setup_key:
            self.setup_visible=False;self.changed.emit()
