"""Bounded local flight history and nonblocking worker-owned observations."""
from collections import deque
import ctypes
from dataclasses import dataclass
import json
import math
import time
import traceback

WINDOW_NS = 60_000_000_000
MAX_CONTEXT_BYTES = 80 * 1024
WORKER_FIELDS = ('accepted_frames','sequence','source_ns','callback_ns','max_source_gap_ns',
                 'max_callback_gap_ns','source_clock_regressions','width','height','resizes')


def _safe(value, depth=0):
    if depth > 8:return '[depth limit]'
    if value is None or type(value) in (bool,int):return value
    if isinstance(value,float):return value if math.isfinite(value) else str(value)
    if isinstance(value,str):return value[:8192]
    if isinstance(value,dict):return {str(k)[:96]:_safe(v,depth+1) for k,v in list(value.items())[:64]}
    if isinstance(value,(tuple,list,deque)):return [_safe(v,depth+1) for v in list(value)[:64]]
    return '[unsupported diagnostic value]'


class FlightRecorder:
    def __init__(self, *, clock=time.perf_counter_ns):
        self.clock=clock
        self.samples=deque(maxlen=61)
        self.events=deque(maxlen=64)
        self.omitted_events=0

    def clear(self):
        self.samples.clear();self.events.clear();self.omitted_events=0

    def _trim(self,now):
        for queue in (self.samples,self.events):
            while queue and queue[0]['qpc_ns'] < now-WINDOW_NS:queue.popleft()

    def sample(self,state,*,now=None):
        now=self.clock() if now is None else now
        self._trim(now);self.samples.append(dict(qpc_ns=now,state=_safe(state)))

    def event(self,name,data=None,*,now=None):
        now=self.clock() if now is None else now
        self._trim(now)
        if len(self.events)==self.events.maxlen:self.omitted_events+=1
        self.events.append(dict(qpc_ns=now,name=str(name)[:64],data=_safe(data or {})))

    def snapshot(self,*,now=None,max_bytes=MAX_CONTEXT_BYTES,context=None):
        now=self.clock() if now is None else now;self._trim(now)
        result=dict(schema=1,qpc_ns=now,window_seconds=60,sample_interval_seconds=1,
                    samples=list(self.samples),events=list(self.events),
                    omitted_samples=0,omitted_events=self.omitted_events,context=_safe(context or {}))
        # Work on a detached copy: stop/restart must not mutate a frozen error.
        result=json.loads(json.dumps(result,ensure_ascii=False,allow_nan=False))
        def size():return len(json.dumps(result,ensure_ascii=False).encode('utf-8'))
        while size()>max_bytes and len(result['samples'])>2:
            old=result['samples'];result['samples']=[old[0],*old[2:-1:2],old[-1]]
            result['omitted_samples']+=len(old)-len(result['samples'])
        while size()>max_bytes and result['events']:
            result['events'].pop(0);result['omitted_events']+=1
        if size()>max_bytes:
            result['context']={'unavailable':'diagnostic byte limit'}
        while size()>max_bytes and result['samples']:
            result['samples'].pop(0);result['omitted_samples']+=1
        return result


@dataclass
class WorkerDiagnostics:
    """One worker writer, GUI reader. Never wait on a failed peer's lock.

    Gap maxima describe accepted capture inputs, including processing/cadence
    delay; they are not independent WGC arrival or physical-input timings.
    """
    state: object
    error: object

    @classmethod
    def create(cls,context):
        return cls(context.RawArray(ctypes.c_longlong,1+len(WORKER_FIELDS)),
                   context.RawArray(ctypes.c_char,16*1024))

    def observe(self,width,height,sequence,source_ns,callback_ns,resizes):
        values=list(self.state[1:]);previous_source,previous_callback=values[2:4]
        values[0]+=1;values[1:4]=[sequence,source_ns,callback_ns]
        if previous_source:
            values[4]=max(values[4],source_ns-previous_source)
            values[6]+=int(source_ns<=previous_source)
        if previous_callback:values[5]=max(values[5],callback_ns-previous_callback)
        values[7:10]=[width,height,resizes]
        self.state[0]+=1;self.state[1:]=values;self.state[0]+=1

    def failure(self,error):
        try:
            data=dict(type=type(error).__name__[:128],message=str(error)[:2048],
                      traceback=''.join(traceback.format_exception(type(error),error,error.__traceback__,limit=12))[-8192:])
            encoded=json.dumps(data,ensure_ascii=False).encode('utf-8')
            while len(encoded)>=len(self.error):
                data['message']=data['message'][:512];data['traceback']=data['traceback'][len(data['traceback'])//2:]
                encoded=json.dumps(data,ensure_ascii=False).encode('utf-8')
            self.state[0]+=1;self.error.value=encoded;self.state[0]+=1
        except Exception:pass  # Diagnostics never replace the worker's original exception.

    def snapshot(self,*,include_failure=True):
        before=self.state[0]
        if before&1:return None
        values=list(self.state[1:]);raw=bytes(self.error.value) if include_failure else b''
        if before!=self.state[0]:return None
        result=dict(zip(WORKER_FIELDS,values))
        result['scope']='accepted_capture_inputs_including_processing_delay; not independent WGC arrivals'
        if raw:
            try:result['failure']=json.loads(raw)
            except (ValueError,UnicodeError):result['failure']={'unavailable':'invalid worker diagnostic'}
        return result
