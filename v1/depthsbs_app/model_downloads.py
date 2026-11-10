"""Qt adapter for an explicitly requested optional model installation."""
from .messages import ErrorMessage as E

from .messages import Message as M, message_value, decode_message, as_error
from .localization import localized, render
import threading
from pathlib import Path
from urllib.error import HTTPError, URLError

from PySide6.QtCore import QObject, Property, Signal, Slot
from PySide6.QtWidgets import QFileDialog

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
        self.updateProgress.connect(self._progress)
        self.finished.connect(self._finished)

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
        return key in PACKS and not available(key, runtime_path() if key == 'vfg'
                                               else self.desktop.engine_paths.get(key))

    @Slot(str, result=str)
    @localized
    def description(self, key):
        if key not in PACKS:
            return ''
        pack = PACKS[key]
        return M('{name} · {size:.0f} MB\n{terms}', name=pack.name, size=pack.size / 1e6, terms=pack.terms)

    @Slot(str, result=str)
    @localized
    def installAction(self, key):
        if key not in PACKS:
            return ''
        try:
            source = source_for(key)
        except FileNotFoundError:
            return ''
        except ValueError:
            return M('Download and install')
        return M('Install local pack') if isinstance(source, Path) else M('Download and install')

    @Slot(str, bool)
    def begin(self, key, choose_file):
        if self.desktop.busy or not self.needed(key):
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
                source = source_for(key)
            self.desktop.lease.acquire('model-install')
        except Exception as exc:
            self.desktop.showModelError(exc)
            return
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
            except (HTTPError, URLError, TimeoutError) as exc:
                self.finished.emit(key, E('E_MODEL_CONNECTION', v0=exc), True)
            except Exception as exc:
                self.finished.emit(key, as_error(exc), True)
            else:
                self.finished.emit(key, '', False)
        threading.Thread(target=work, name='DepthSBS model install', daemon=True).start()

    @Slot()
    def cancel(self):
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
        if not message and key != 'vfg':
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
