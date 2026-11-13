"""Owned media children: bounded diagnostics and cancellation during pipe I/O."""
from collections import deque
import os
import subprocess
import sys
import threading

from .messages import ErrorMessage as E


class PipeCapture:
    def __init__(self,stream,*,limit=65536,tail=True):
        self.stream,self.limit,self.tail=stream,limit,tail
        self.chunks=deque();self.size=0;self.overflow=False;self.error=None
        self.thread=threading.Thread(target=self._drain,name='ScreenTo3D media pipe',daemon=True)
        self.thread.start()

    def _drain(self):
        try:
            read=getattr(self.stream,'read1',self.stream.read)
            while chunk:=read(4096):
                if self.tail:
                    self.chunks.append(chunk);self.size+=len(chunk)
                    while self.size>self.limit:self.size-=len(self.chunks.popleft())
                else:
                    remaining=max(0,self.limit-self.size)
                    if len(chunk)>remaining:self.overflow=True
                    if remaining:self.chunks.append(chunk[:remaining]);self.size+=min(remaining,len(chunk))
        except Exception as error:self.error=error

    def read(self,timeout=30):
        self.thread.join(timeout)
        if self.thread.is_alive():raise RuntimeError(E('E_MEDIA_PROCESS',details='Media pipe did not close.'))
        if self.error is not None:raise RuntimeError(E('E_MEDIA_PROCESS',details=str(self.error)))
        if self.overflow:raise RuntimeError(E('E_MEDIA_PROCESS',details='Media metadata exceeded its size limit.'))
        return b''.join(self.chunks)


class MediaChild:
    def __init__(self,process):
        self.process=process;self.closed=False
        self.stdin,self.stdout=process.stdin,process.stdout
        self.stderr=PipeCapture(process.stderr)

    def poll(self):return self.process.poll()
    def wait(self,timeout=30):return self.process.wait(timeout=timeout)
    def kill(self):return self.process.kill()

    def close(self):
        if self.closed:return []
        errors=[];reaped=False
        try:
            if self.poll() is None:self.kill()
            self.wait(timeout=5)
            reaped=True
        except Exception as error:errors.append(error)
        if not reaped:return errors  # Do not block closing a live child's pipe.
        try:self.stderr.read(timeout=5)
        except Exception as error:errors.append(error)
        if self.stderr.thread.is_alive():return errors
        for stream in (self.process.stdin,self.process.stdout,self.process.stderr):
            if stream is not None:
                try:stream.close()
                except Exception as error:errors.append(error)
        self.closed=True
        return errors


def cleanup_processes(processes):
    errors=[]
    for process in processes:
        if process is None:continue
        if isinstance(process,MediaChild):
            errors.extend(process.close());continue
        try:
            if process.poll() is None:process.kill()
            process.wait(timeout=5)
        except Exception as error:errors.append(error)
        for name in ('stdin','stdout','stderr'):
            stream=getattr(process,name,None)
            if stream is not None:
                try:stream.close()
                except Exception as error:errors.append(error)
    return errors


class MediaProcesses:
    """One file job; only children created here can be killed on cancellation."""
    def __init__(self,cancel_path=None):
        self.cancel_path=cancel_path;self.children=[];self.lock=threading.Lock()
        self.stop=threading.Event();self.cancelled=threading.Event();self.watcher=None
        self.closed=False

    def __enter__(self):
        if self.cancel_path is not None:
            self.watcher=threading.Thread(target=self._watch,name='ScreenTo3D media cancel',daemon=True)
            self.watcher.start()
        return self

    def _watch(self):
        while not self.stop.wait(.05):
            if self.cancel_path.exists():
                self.cancelled.set()
                with self.lock:children=tuple(self.children)
                for child in children:
                    try:
                        if not child.closed and child.poll() is None:child.kill()
                    except OSError:pass  # Main-thread cleanup reports any surviving child.

    def check_cancel(self):
        if self.cancelled.is_set() or self.cancel_path is not None and self.cancel_path.exists():
            raise InterruptedError('Conversion cancelled')

    def spawn(self,arguments,**kwargs):
        self.check_cancel()
        process=subprocess.Popen(arguments,**kwargs)
        try:child=MediaChild(process)
        except BaseException:
            cleanup_processes((process,));raise
        with self.lock:self.children.append(child)
        self.check_cancel()
        return child

    def run(self,arguments):
        child=self.spawn(arguments,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        output=PipeCapture(child.stdout,limit=4*1024*1024,tail=False)
        try:
            while True:
                self.check_cancel()
                try:code=child.wait(timeout=.1);break
                except subprocess.TimeoutExpired:continue
            self.check_cancel()
            return subprocess.CompletedProcess(arguments,code,output.read().decode('utf-8','replace'),child.stderr.read().decode('utf-8','replace'))
        finally:
            primary=sys.exception()
            errors=child.close()
            try:output.read(timeout=5)
            except Exception as error:errors.append(error)
            if errors:
                failure=ExceptionGroup('Media process cleanup failed',errors)
                if primary is not None:primary.add_note(repr(failure))
                else:raise failure

    def finish(self):
        if self.closed:return []
        errors=cleanup_processes(self.children)
        self.stop.set()
        if self.watcher is not None:
            self.watcher.join(1)
            if self.watcher.is_alive():errors.append(RuntimeError('Media cancellation watcher did not stop.'))
        self.closed=True
        return errors

    def __exit__(self,kind,error,traceback):
        errors=self.finish()
        if errors:
            failure=ExceptionGroup('Media process cleanup failed',errors)
            if error is not None:error.add_note(repr(failure))
            else:raise failure
