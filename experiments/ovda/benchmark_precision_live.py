# oVDA native benchmark, NC-SA-UHDV1.0; see LICENSE/README.md.
"""Owned public source -> actual WGC -> oVDA -> native SBS, reversed trial order."""
import argparse
import ctypes as ct
from functools import partial
import json
from pathlib import Path
import statistics
import time

from trial_runtime import trial_sbs_worker


def range_sbs_worker(mode,*args,**kwargs):
    import os
    from dataclasses import replace
    from unittest.mock import patch
    from depthsbs_app import live_model
    if mode not in ('range-legacy','range-stable'):raise ValueError('Invalid range comparison')
    kwargs['gpu_capture_snapshot']=True
    adapter=replace(live_model.model_adapter('ovda-small-c16'),temporal_depth_alpha=.5,
                    stabilize_depth_range=mode=='range-stable')
    with patch.dict(live_model._MODELS,{'ovda-small-c16':adapter}),patch.dict(os.environ,{'DEPTHSBS_DEPTH_HISTORY':'continuous'}):
        return trial_sbs_worker('fp32-current',*args,**kwargs)


def ema_sbs_worker(mode,*args,**kwargs):
    import os
    from dataclasses import replace
    from unittest.mock import patch
    from depthsbs_app import live_model
    weights={'ema-0.18':.18,'ema-0.5':.5}
    if mode not in weights:raise ValueError('Invalid EMA comparison')
    kwargs['gpu_capture_snapshot']=True
    adapter=replace(live_model.model_adapter('ovda-small-c16'),temporal_depth_alpha=weights[mode],stabilize_depth_range=False)
    with patch.dict(live_model._MODELS,{'ovda-small-c16':adapter}),patch.dict(os.environ,{'DEPTHSBS_DEPTH_HISTORY':'continuous'}):
        return trial_sbs_worker('fp32-current',*args,**kwargs)


def history_sbs_worker(mode,*args,**kwargs):
    import os
    from unittest.mock import patch
    if mode not in ('history-strict','history-short-skip'):raise ValueError('Invalid history comparison')
    kwargs['gpu_capture_snapshot']=True
    with patch.dict(os.environ,{'DEPTHSBS_DEPTH_HISTORY':'legacy' if mode=='history-strict' else 'continuous'}):
        return trial_sbs_worker('fp32-current',*args,**kwargs)


def capture_sbs_worker(enabled, variant, *args, **kwargs):
    # The controller supplies its own immutable snapshot. Override inside the
    # child target, rather than a partial keyword that the caller can replace.
    kwargs['gpu_capture_snapshot']=enabled
    return trial_sbs_worker(variant,*args,**kwargs)


class Utilization(ct.Structure):
    _fields_=[('gpu',ct.c_uint),('memory',ct.c_uint)]


class GpuMonitor:
    def __init__(self):
        self.lib=ct.WinDLL('C:/Windows/System32/nvml.dll')
        self.lib.nvmlDeviceGetHandleByIndex_v2.argtypes=[ct.c_uint,ct.POINTER(ct.c_void_p)]
        self.lib.nvmlDeviceGetUtilizationRates.argtypes=[ct.c_void_p,ct.POINTER(Utilization)]
        self.handle=ct.c_void_p()
        if self.lib.nvmlInit_v2() or self.lib.nvmlDeviceGetHandleByIndex_v2(0,ct.byref(self.handle)):
            raise RuntimeError('NVML initialization failed')
    def sample(self):
        values=Utilization()
        if self.lib.nvmlDeviceGetUtilizationRates(self.handle,ct.byref(values)):
            raise RuntimeError('NVML sampling failed')
        return values.gpu
    def close(self):self.lib.nvmlShutdown()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--capture-comparison',action='store_true',help='Fresh FP32 with CPU versus GPU capture/input')
    parser.add_argument('--runtime-comparison',action='store_true',help='GPU input before/after runtime buffer cleanup')
    parser.add_argument('--history-comparison',action='store_true',help='Strict capture-index resets versus bounded oVDA short skips')
    parser.add_argument('--ema-comparison',action='store_true',help='oVDA independent pixel EMA .18 versus .5 with retained history')
    parser.add_argument('--range-comparison',action='store_true',help='oVDA legacy versus anchored source-time range; pixel EMA fixed .5')
    parser.add_argument('--resolution-comparison',action='store_true',help='518/392 FP32 and mixed FP16, current stable live path')
    parser.add_argument('--layout',choices=('full-sbs','half-tb'),default='full-sbs')
    parser.add_argument('--windows',type=int,choices=(2,3),default=2)
    args=parser.parse_args()
    if sum((args.capture_comparison,args.runtime_comparison,args.history_comparison,args.ema_comparison,args.range_comparison,args.resolution_comparison))>1:parser.error('Choose one comparison')
    args.output.mkdir(parents=True,exist_ok=False)
    from depthsbs_app import live_sbs
    from depthsbs_app.desktop import create_app
    from depthsbs_app.desktop_preferences import DesktopPreferences
    from PySide6.QtCore import QSettings
    from live_benchmark_source import SourceProcess
    import shiboken6
    app,engine,desktop=create_app(DesktopPreferences(QSettings(str((args.output/'preferences.ini').resolve()),QSettings.IniFormat)))
    live=desktop.live
    live.setMode('video-quality');live.setLiveModel('ovda-small-c16');live.setOvdaConfirmed(True)
    live.setPresentationHz(0);live.setStereoLayout(args.layout)
    live.output_placement.path=args.output/'placement.json'
    errors=[];live.errorOccurred.connect(errors.append)
    source=None;monitor=GpuMonitor()
    report=dict(rows=[],source='owned FloorballGame preview at 16ms timer',cap=0,
                gpu_scope='device-wide utilization includes public source, desktop and other clients',
                fps_scope='distinct native output submissions, not physical presentation',warmup_seconds=3,window_seconds=3,
                capture_comparison=args.capture_comparison,runtime_comparison=args.runtime_comparison,
                history_comparison=args.history_comparison,ema_comparison=args.ema_comparison,range_comparison=args.range_comparison,
                resolution_comparison=args.resolution_comparison,layout=args.layout)
    original=live_sbs.sbs_worker

    def pump(seconds):
        until=time.monotonic()+seconds
        while time.monotonic()<until:
            app.processEvents();time.sleep(.002)
    def wait(predicate,seconds=90):
        until=time.monotonic()+seconds
        while not predicate() and time.monotonic()<until:
            pump(.02)
            if errors:raise RuntimeError(errors[-1])
        if not predicate():raise TimeoutError(live.status)
    def count():
        return live.native.report()['output']['submitted_frames'] if live.native is not None else 0
    def stop():
        live.stop()
        until=time.monotonic()+20
        while live.active and time.monotonic()<until:pump(.02)
        if live.active:raise TimeoutError('Owned worker stop timed out')
        pump(.1)
        native=live.native.report()
        assert native['live_pools']==native['live_nodes']==0,native

    try:
        source=SourceProcess('FloorballGame',interval_ms=16)
        for width,height in ((1920,1080),(3840,2160)):
            source.resize(round(width/source.devicePixelRatioF()),round(height/source.devicePixelRatioF()))
            source.request('activate');pump(.3)
            variants=(('fp32-current','encoder-spatial','low-fp32','low-fp16') if args.resolution_comparison else
                      ('range-legacy','range-stable') if args.range_comparison else
                      ('ema-0.18','ema-0.5') if args.ema_comparison else
                      ('history-strict','history-short-skip') if args.history_comparison else
                      ('runtime-before','runtime-after') if args.runtime_comparison else
                      ('cpu-input','gpu-input') if args.capture_comparison else ('fp32-current','encoder','encoder-spatial'))
            for order in (variants,tuple(reversed(variants))):
                for variant in order:
                    desktop.main_window.setTitle('oVDA precision experiment · '+variant)
                    gpu_capture=variant=='gpu-input' or args.runtime_comparison or args.history_comparison or args.ema_comparison or args.range_comparison or args.resolution_comparison
                    if args.range_comparison:
                        live_sbs.sbs_worker=partial(range_sbs_worker,variant)
                    elif args.ema_comparison:
                        live_sbs.sbs_worker=partial(ema_sbs_worker,variant)
                    elif args.history_comparison:
                        live_sbs.sbs_worker=partial(history_sbs_worker,variant)
                    elif args.runtime_comparison:
                        from runtime_trial import runtime_sbs_worker
                        live_sbs.sbs_worker=partial(runtime_sbs_worker,variant)
                    else:
                        live_sbs.sbs_worker=partial(capture_sbs_worker,gpu_capture,
                                                   'fp32-current' if args.capture_comparison else variant)
                    live.items=[dict(kind='window',id=int(source.winId()),pid=source.pid,label='Owned oVDA trial source',
                                     width=width,height=height)]
                    live.select(0);live.startMinimal()
                    wait(lambda:count()>=5)
                    from depthsbs_app.stereo_layout import dimensions
                    assert live.active and live.meta[2:4]==list(dimensions(width,height,args.layout)),live.meta
                    pump(3)
                    rows=[]
                    for window in range(args.windows):
                        source_before=source.refresh()
                        stats_before=live._stats()
                        before=count();started=time.monotonic();samples=[];next_sample=started
                        while time.monotonic()-started<3:
                            pump(.02)
                            if errors:raise RuntimeError(errors[-1])
                            if time.monotonic()>=next_sample:
                                samples.append(monitor.sample());next_sample+=.5
                        after=count();elapsed=time.monotonic()-started
                        stats_after=live._stats()
                        source_after=source.refresh()
                        uploaded=stats_after[live_sbs.H2D_BYTES]-stats_before[live_sbs.H2D_BYTES]
                        assert (uploaded==0) if gpu_capture else (uploaded>0), 'Capture path transfer contract mismatch'
                        rows.append(dict(fps=(after-before)/elapsed,gpu_mean=statistics.mean(samples),
                                         native_frames=after-before,elapsed=elapsed,
                                         source_fps=(source_after['sequence']-source_before['sequence'])/elapsed,
                                         inferred_fps=(stats_after[live_sbs.INFERRED]-stats_before[live_sbs.INFERRED])/elapsed,
                                         h2d_bytes=uploaded,
                                         d2h_bytes=stats_after[live_sbs.D2H_BYTES]-stats_before[live_sbs.D2H_BYTES],
                                         resets=stats_after[live_sbs.RESETS]-stats_before[live_sbs.RESETS]))
                        if args.history_comparison or args.ema_comparison or args.range_comparison or args.resolution_comparison:
                            n=stats_after[live_sbs.INFERRED]-stats_before[live_sbs.INFERRED]
                            rows[-1].update(
                                reset_gap=stats_after[live_sbs.RESET_GAP]-stats_before[live_sbs.RESET_GAP],
                                reset_cut=stats_after[live_sbs.RESET_CUT]-stats_before[live_sbs.RESET_CUT],
                                retained_gaps=stats_after[live_sbs.OVDA_RETAINED_GAPS]-stats_before[live_sbs.OVDA_RETAINED_GAPS],
                                cached_past_mean=(stats_after[live_sbs.OVDA_CACHE_SUM]-stats_before[live_sbs.OVDA_CACHE_SUM])/max(1,n),
                                full_context_fraction=(stats_after[live_sbs.OVDA_FULL_CONTEXT]-stats_before[live_sbs.OVDA_FULL_CONTEXT])/max(1,n),
                                maximum_update_streak=stats_after[live_sbs.OVDA_STREAK_MAX])
                    row=dict(size=[width,height],variant=variant,windows=rows,source_state=source.refresh()['sequence'],
                             gpu_capture=gpu_capture,processed=live._stats()[0])
                    report['rows'].append(row)
                    (args.output/'report.json').write_text(json.dumps(report,indent=2))
                    print(json.dumps(row),flush=True)
                    stop()
        report['completed']=True
    except BaseException as error:
        report['error']=str(error)
        raise
    finally:
        if live.active:stop()
        if source is not None:source.close()
        live_sbs.sbs_worker=original
        monitor.close()
        (args.output/'report.json').write_text(json.dumps(report,indent=2))
        shiboken6.delete(engine)


if __name__=='__main__':main()
