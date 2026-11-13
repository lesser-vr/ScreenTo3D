"""Explicit, one-shot completion shutdown with an app-owned cancelable countdown."""
import math
import os
from pathlib import Path
import time

from PySide6.QtCore import QObject,Property,Signal,Slot,QTimer,QProcess
from .messages import Message as M,ErrorMessage as E
from .localization import localized


def shutdown_command():
    if os.name!='nt':
        raise RuntimeError(E('E_SHUTDOWN_UNSUPPORTED'))
    import ctypes
    from ctypes import wintypes
    library=ctypes.WinDLL('kernel32',use_last_error=True)
    library.GetSystemDirectoryW.argtypes=[wintypes.LPWSTR,wintypes.UINT]
    library.GetSystemDirectoryW.restype=wintypes.UINT
    buffer=ctypes.create_unicode_buffer(32768)
    count=library.GetSystemDirectoryW(buffer,len(buffer))
    if not count or count>=len(buffer):
        raise OSError(E('E_SHUTDOWN_FAILED'))
    # A positive OS timeout implies forced app closure. Keep the delay in our UI,
    # then request an ordinary shutdown without /f or shell/PATH lookup.
    return str(Path(buffer.value)/'shutdown.exe'),['/s','/t','0','/d','p:0:0']


class CompletionShutdown(QObject):
    changed=Signal()
    countdownStarted=Signal()
    errorOccurred=Signal(object)

    def __init__(self,lease,parent=None,*,clock=time.monotonic,command=shutdown_command,process_factory=QProcess):
        super().__init__(parent)
        self.lease,self.clock,self.command=lease,clock,command
        self.process_factory=process_factory
        self.selected_value=False
        self.deadline=None
        self.process=None
        self.seconds=0
        self.message=''
        self.timer=QTimer(self);self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)

    @Property(bool,notify=changed)
    def selected(self):return self.selected_value

    @Property(bool,notify=changed)
    def pending(self):return self.deadline is not None

    @Property(str,notify=changed)
    @localized
    def status(self):
        return M('All conversions succeeded. Windows will shut down in {seconds} seconds.',seconds=self.seconds) if self.pending else self.message

    @Slot(bool)
    def setSelected(self,selected):
        if self.process is not None or self.lease.owner not in (None,'shutdown'):
            return
        if not selected:
            self.cancel()
        else:
            self.selected_value=True;self.changed.emit()

    def begin(self):
        if not self.selected_value or self.pending or self.process is not None:
            return
        self.lease.acquire('shutdown')
        self.deadline=self.clock()+30
        self.seconds=30
        self.timer.start();self.changed.emit();self.countdownStarted.emit()

    @Slot()
    def cancel(self):
        if self.process is not None:
            return  # The countdown has ended and an OS request is in flight.
        was_pending=self.pending
        self.timer.stop();self.deadline=None;self.selected_value=False
        if self.lease.owner=='shutdown':self.lease.release('shutdown')
        if was_pending:self.message=M('Windows shutdown cancelled.')
        self.changed.emit()

    def _tick(self):
        if not self.pending:return
        self.seconds=max(0,math.ceil(self.deadline-self.clock()))
        if self.seconds:
            self.changed.emit();return
        self.timer.stop();self.deadline=None
        try:
            if not self.selected_value or self.lease.owner!='shutdown':
                self.cancel();return
            program,args=self.command()
            process=self.process_factory(self);self.process=process
            process.setProgram(program);process.setArguments(args)
            process.readyReadStandardOutput.connect(lambda:process.readAllStandardOutput())
            process.readyReadStandardError.connect(lambda:process.readAllStandardError())
            process.finished.connect(lambda code,status:self._finish(code==0 and status==QProcess.NormalExit) if self.process is process else None)
            process.errorOccurred.connect(lambda error:self._finish(False) if error==QProcess.FailedToStart and self.process is process else None)
            self.message=M('Requesting Windows shutdown…')
            process.start();self.changed.emit()
        except Exception:
            self._finish(False)

    def _finish(self,success):
        self.timer.stop();self.deadline=None;self.selected_value=False
        if self.process is not None:self.process.deleteLater()
        self.process=None
        if self.lease.owner=='shutdown':self.lease.release('shutdown')
        self.message=M('Windows shutdown requested.') if success else E('E_SHUTDOWN_FAILED')
        self.changed.emit()
        if not success:self.errorOccurred.emit(self.message)
