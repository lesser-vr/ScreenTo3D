"""GUI-owned diagnostic sampling; no pixels, GPU waits or success-path writes."""
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os
import traceback
from pathlib import Path
import sys
import time
import uuid
from PySide6.QtCore import QObject,QTimer,Qt
from PySide6.QtGui import QGuiApplication,QWindow
from .live_diagnostics import FlightRecorder
from .capture_mailbox import SEQ,RECEIVED,SOURCE_NS,CALLBACK_NS,RESIZES,WIDTH,HEIGHT
from .live_sbs import GPU_USAGE,GPU_USAGE_NS,SBS_REUSED


class LiveDiagnosticRecorder(QObject):
    def __init__(self,live):
        super().__init__(live);self.live=live;self.flight=FlightRecorder()
        self.pending=None;self.identity=None;self.run_id=uuid.uuid4().hex;self.failures=0
        self.timer=QTimer(self);self.timer.setTimerType(Qt.PreciseTimer);self.timer.setInterval(1000);self.timer.timeout.connect(self.sample)
        live.changed.connect(self.sync)

    def _attempt(self,action,*args,**kwargs):
        try:return action(*args,**kwargs)
        except Exception:self.failures+=1;return None

    def begin(self,*,restart=False):
        def work():
            if not restart:self.flight.clear()
            self.pending=None
            self._attempt(self.build_identity)
            self.flight.event('start_requested',dict(restart=restart,settings=self.configuration()))
            self.timer.start()
        self._attempt(work)

    def sync(self):
        if not self.live.active:self.timer.stop()
        elif not self.timer.isActive():self.timer.start()

    def source(self):
        live=self.live
        if live.active and live.source:return live.source
        return live.items[live.selected] if 0<=live.selected<len(live.items) else {}

    def configuration(self):
        live=self.live;s=self.source()
        return dict(session=live.session,model=live.live_model,mode=live.mode,
                    layout=live.stereo_layout,limit_hz=live.cadence.hz,strength=live.strength,
                    vfg=live.vfg_enabled,vfg_switching=live.vfgSwitching,
                    native=live.nativeEnabled,gpu_capture=live.gpu_capture_selected,
                    source={key:s.get(key) for key in ('kind','id','pid','width','height')})

    def screens(self):
        return [dict(name=s.name(),rect=[s.geometry().x(),s.geometry().y(),s.geometry().width(),s.geometry().height()],
                     dpr=s.devicePixelRatio(),refresh_hz=s.refreshRate()) for s in QGuiApplication.screens()]

    def source_state(self):
        source=self.source();kind=source.get('kind');result=dict(kind=kind)
        if kind=='window':
            from .capture_sources import user32
            hwnd=int(source['id']);pid=W.DWORD();user32.GetWindowThreadProcessId(hwnd,C.byref(pid))
            valid=bool(user32.IsWindow(hwnd) and pid.value==source['pid'])
            result.update(valid=valid,pid_matches=pid.value==source['pid'])
            if valid:
                user32.GetClientRect.argtypes=[W.HWND,C.POINTER(W.RECT)]
                rect=W.RECT();sized=bool(user32.GetClientRect(hwnd,C.byref(rect)))
                result.update(visible=bool(user32.IsWindowVisible(hwnd)),minimized=bool(user32.IsIconic(hwnd)),
                              client_px=[rect.right-rect.left,rect.bottom-rect.top] if sized else None)
        elif kind=='monitor':result['selected_px']=[source.get('width'),source.get('height')]
        return result

    def state(self):
        live=self.live;meta=list(live.meta);stats=live._stats();window=live.output_window
        native=(self._attempt(live.native.report) or {}) if live.native is not None else {}
        producer=getattr(live,'diagnostic_worker',None)
        worker=producer.snapshot(include_failure=False) if producer is not None else None
        if worker:worker.pop('scope',None)
        pool=getattr(live.native,'pool',None)
        output=self._attempt(self.output_state,window,native,meta,pool)
        return dict(session=live.session,active=live.active,stopping=live.stopping,
                    worker_pid=live.process.pid if live.process is not None else None,
                    source=self._attempt(self.source_state),capture=dict(received=meta[RECEIVED],sequence=meta[SEQ],
                    source_ns=meta[SOURCE_NS],callback_ns=meta[CALLBACK_NS],resizes=meta[RESIZES]),
                    processing=dict(frames=stats[0],inferences=stats[10],reused_sbs=stats[SBS_REUSED],resets=list(stats[30:34])),
                    gpu=dict(percent=stats[GPU_USAGE],qpc_ns=stats[GPU_USAGE_NS],scope='whole_device_existing_sampler'),
                    output=output,
                    accepted_capture=worker)

    def output_state(self,window,native,meta,pool):
        return dict(visible=bool(window and window.isVisible()),
                    fullscreen=bool(window and window.visibility()==QWindow.FullScreen),
                    buffer_px=[meta[WIDTH],meta[HEIGHT]],
                    window_rect=[window.x(),window.y(),window.width(),window.height()] if window else None,
                    submitted=native.get('output',{}).get('submitted_frames',self.live.submitted),
                    pools=native.get('live_pools'),nodes=native.get('live_nodes'),generation=getattr(pool,'generation',None))

    def sample(self):
        return self._attempt(lambda:self.flight.sample(self.state()))

    def note(self,name,**data):
        return self._attempt(lambda:self.flight.event(name,data))

    def build_identity(self):
        if self.identity is not None:return self.identity
        from . import __version__
        from .user_data import APP_ROOT
        source=Path(__file__).with_name('live_preview.py')
        identity=dict(run_id=self.run_id,pid=os.getpid(),app_version=__version__,
                      executable=str(Path(sys.executable).resolve()),app_root=str(APP_ROOT),
                      live_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
        identity['source_sha256']={name:hashlib.sha256(source.with_name(name).read_bytes()).hexdigest()
            for name in ('desktop.py','live_sbs.py','live_diagnostics.py','live_diagnostic_state.py')}
        manifest=APP_ROOT/'build-manifest.json'
        if manifest.is_file() and manifest.stat().st_size<=1024*1024:
            data=json.loads(manifest.read_text(encoding='utf-8'))
            identity['build']={k:data.get(k) for k in ('product_version','source_commit','source_dirty')}
        self.identity=identity;return identity

    def freeze(self,trigger,*,error=None):
        def work():
            self.flight.event(trigger);self.sample()
            worker=getattr(self.live,'diagnostic_worker',None)
            exception=None
            if isinstance(error,BaseException):
                exception=dict(type=type(error).__name__,message=str(error)[:2048],
                    traceback=''.join(traceback.format_exception(type(error),error,error.__traceback__,limit=12))[-8192:])
            self.pending=self.flight.snapshot(context=dict(trigger=trigger,identity=self._attempt(self.build_identity),exception=exception,
                settings=self._attempt(self.configuration),screens=self._attempt(self.screens),sampling_failures=self.failures,
                worker=worker.snapshot() if worker is not None else None,
                scope='sampled metadata and accepted capture counters; no pixels, independent WGC arrival timing or optical latency'))
        self._attempt(work)

    def take_error(self,message):
        if self.pending is None:self.freeze('reported_error')
        result=self.pending;self.pending=None
        return result
