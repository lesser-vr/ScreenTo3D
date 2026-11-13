"""GUI-owned explicit portable import, sharing the existing processing lease."""
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject,Property,Signal,Slot,QUrl
from PySide6.QtGui import QDesktopServices

from .localization import localized
from .messages import Message as M,ErrorMessage as E,as_error
from .portable_import import inventory,import_files
from .user_data import data_root,legacy_roots


class DataManager(QObject):
    changed=Signal()
    progressReady=Signal(int)
    finished=Signal(object,object)

    def __init__(self,desktop):
        super().__init__(desktop);self.desktop=desktop;self.visible=False;self.running=False
        self.percent=0;self.message='';self.sources=[];self.items=[]
        self.stop=threading.Event();self.thread=None
        self.progressReady.connect(self._progress);self.finished.connect(self._finished)

    @Property(bool,notify=changed)
    def shown(self):return self.visible
    @Property(bool,notify=changed)
    def active(self):return self.running
    @Property(int,notify=changed)
    def progress(self):return self.percent
    @Property(str,constant=True)
    def path(self):return str(data_root())
    @Property(str,notify=changed)
    @localized
    def status(self):return self.message
    @Property(str,notify=changed)
    def sourcePaths(self):return '\n'.join(map(str,self.sources))
    @Property(float,notify=changed)
    def sourceGB(self):return sum(item['bytes'] for item in self.items)/1e9

    def offer(self):
        offered=self.desktop.preferences.store.value('portable/importOffered',False)
        if offered not in (True,'true','1',1) and legacy_roots():self.open()

    @Slot()
    def open(self):
        if self.running:self.visible=True;self.changed.emit();return
        try:
            self.sources=legacy_roots();self.items=inventory(self.sources)
            from .user_data import APP_ROOT,_check
            old=APP_ROOT/'out/desktop-output-placement.json'
            if old.is_file() and not (data_root()/'window-state.json').exists():
                _check(old,APP_ROOT/'out');stat=old.stat()
                self.items.append(dict(source=old.parent,path=old,relative=Path('window-state.json'),bytes=stat.st_size,mtime=stat.st_mtime_ns))
                self.sources.append(old.parent)
            self.message=M('Existing files can be copied and verified here. Current files and settings take priority.')
            self.visible=True;self.changed.emit()
        except Exception as error:self.desktop.showModelError(as_error(error))

    @Slot()
    def dismiss(self):
        if self.running:self.cancel();return
        self.visible=False
        self.desktop.preferences.store.setValue('portable/importOffered',True)
        self.desktop.preferences.store.sync();self.changed.emit()

    @Slot()
    def openFolder(self):QDesktopServices.openUrl(QUrl.fromLocalFile(str(data_root())))

    @Slot(bool,bool)
    def begin(self,settings=True,cleanup=False):
        if self.running or self.desktop.busy:return
        try:
            # Use exactly the displayed inventory; changed sources fail validation.
            self.desktop.lease.acquire('data-import')
        except Exception as error:self.desktop.showModelError(as_error(error));return
        self.running=True;self.percent=0;self.stop.clear()
        self.message=M('Copying and verifying existing data…');self.changed.emit();self.desktop.changed.emit()
        items=list(self.items)
        def work():
            report=None;error=None;last=[0.]
            def progress(done,total):
                now=time.monotonic()
                if now-last[0]>=.05 or done==total:
                    self.progressReady.emit(round(done*100/max(1,total)));last[0]=now
            try:
                from .portable_settings import read_legacy_settings
                values=read_legacy_settings() if settings else {}
                report=import_files(items,progress,self.stop.is_set,cleanup=cleanup)
                report['settings']=values
            except Exception as exc:error=as_error(exc)
            self.finished.emit(report,error)
        self.thread=threading.Thread(target=work,name='ScreenTo3D portable import',daemon=False);self.thread.start()

    @Slot()
    def cancel(self):
        self.stop.set();self.message=M('Cancelling after the current file operation…');self.changed.emit()

    @Slot(int)
    def _progress(self,value):self.percent=value;self.changed.emit()

    @Slot(object,object)
    def _finished(self,report,error):
        self.running=False;self.thread=None
        self.desktop.lease.release('data-import')
        if error is None:
            try:
                from .portable_settings import adopt_settings
                adopt_settings(self.desktop.preferences.store,report['settings'])
                self.desktop.refreshImportedData()
                self.message=M('Imported {files} files · {conflicts} conflicts kept · {removed} originals removed · {preserved} originals retained',
                    files=report['files'],conflicts=report['conflicts'],removed=report['removed'],preserved=report['preserved'])
                self.percent=100
            except Exception as exc:error=as_error(exc)
        if error is not None:
            self.message=error
            if getattr(error,'error_id','')!='E_DATA_IMPORT_CANCELLED':self.desktop.showModelError(error)
        self.desktop.preferences.store.setValue('portable/importOffered',True);self.desktop.preferences.store.sync()
        self.changed.emit();self.desktop.changed.emit()
        if self.desktop.closing:self.desktop.exitReady.emit()
