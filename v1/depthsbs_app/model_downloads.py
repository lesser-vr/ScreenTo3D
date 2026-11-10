"""Qt adapter for an explicitly requested optional model installation."""
import threading
from pathlib import Path
from urllib.error import HTTPError, URLError

from PySide6.QtCore import QObject, Property, Signal, Slot
from PySide6.QtWidgets import QFileDialog

from .optional_models import PACKS, available, install, installed_path, source_for
from .vfg_runtime import BRIDGE, runtime_path


class ModelDownloads(QObject):
    changed = Signal()
    updateProgress = Signal(str, int)
    finished = Signal(str, str, bool)

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
    def activeKey(self):
        return self.active_key

    @Property(str, notify=changed)
    def lastKey(self):
        return self.last_key

    @Property(str, notify=changed)
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
    def description(self, key):
        if key not in PACKS:
            return ''
        pack = PACKS[key]
        return f'{pack.name} · {pack.size / 1e6:.0f} MB\n{pack.terms}'

    @Slot(str, result=str)
    def installAction(self, key):
        if key not in PACKS:
            return ''
        try:
            source = source_for(key)
        except FileNotFoundError:
            return ''
        except ValueError:
            return '다운로드 및 설치'
        return '로컬 팩 설치' if isinstance(source, Path) else '다운로드 및 설치'

    @Slot(str, bool)
    def begin(self, key, choose_file):
        if self.desktop.busy or not self.needed(key):
            return
        if key == 'vfg' and not BRIDGE.is_file():
            self.desktop.showModelError('VFG 출력 모듈이 없습니다. ScreenTo3D 배포본을 다시 설치하세요.')
            return
        try:
            if choose_file:
                filename, _ = QFileDialog.getOpenFileName(None, '모델 설치 파일 선택', '',
                                                          f'설치 파일 ({PACKS[key].filename})')
                if not filename:
                    return
                source = Path(filename)
            else:
                source = source_for(key)
            self.desktop.lease.acquire('model-install')
        except Exception as exc:
            self.desktop.showModelError(str(exc))
            return
        self.active_key, self.message, self.percent = key, '연결 중…', -1
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
                self.finished.emit(key, '설치를 취소했습니다.', False)
            except (HTTPError, URLError, TimeoutError) as exc:
                self.finished.emit(key, f'모델 서버에 연결할 수 없습니다. 다시 시도하거나 설치 파일을 선택하세요.\n{exc}', True)
            except Exception as exc:
                self.finished.emit(key, str(exc), True)
            else:
                self.finished.emit(key, '', False)
        threading.Thread(target=work, name='DepthSBS model install', daemon=True).start()

    @Slot()
    def cancel(self):
        self.stop_event.set()
        self.message = '설치 취소 중…'
        self.changed.emit()

    @Slot(str, int)
    def _progress(self, message, percent):
        if not self.stop_event.is_set():
            self.message, self.percent = message, percent
            self.changed.emit()

    @Slot(str, str, bool)
    def _finished(self, key, message, failed):
        if not message and key != 'vfg':
            path = str(installed_path(key))
            self.desktop.engine_paths[key] = path
            if self.desktop.values['model'] == key:
                self.desktop.values['engine'] = path
        self.active_key = ''
        self.message = message or f'{PACKS[key].name} 설치 완료'
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
