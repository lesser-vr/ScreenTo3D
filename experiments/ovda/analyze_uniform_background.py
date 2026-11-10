# oVDA bottleneck diagnostic, NC-SA-UHDV1.0; see LICENSE/README.md.
"""Actual local clip/WGC/native ablation; no product policy or model changes."""
import argparse
from collections import deque
from contextlib import ExitStack
from dataclasses import replace
from functools import partial
import hashlib
import json
import os
from pathlib import Path
import statistics
import time
from unittest.mock import patch


def worker(background,*args,history_trace=None,history_policy=None,**kwargs):
    from depthsbs_app import live_sbs,live_policy
    original=live_policy.resolve_live
    def resolve(*values,**options):
        policy=original(*values,**options)
        return policy if background is None else replace(policy,flat_background_refinement=background)
    kwargs['gpu_capture_snapshot']=True
    samples=deque(maxlen=2048);seen=0;previous_decision=None
    original_reason=live_sbs.reset_reason
    stats=args[3]
    def trace_reason(*values,**options):
        nonlocal seen,previous_decision
        now=time.perf_counter_ns();reason=original_reason(*values,**options)
        previous,sequence,previous_shape,shape,cut=values
        source=options.get('source_ns');prior_source=options.get('previous_source_ns')
        alternate=dict(options,vda_single_skip=True,ovda_short_skip=False,allow_coalescing=False)
        samples.append(dict(index=seen,processed=stats[live_sbs.PROCESSED],size=list(shape),
            reason=reason,cut=bool(cut),sequence_step=sequence-previous if previous is not None else None,
            source_step_ns=source-prior_source if prior_source is not None else None,
            decision_interval_ns=now-previous_decision if previous_decision is not None else None,
            previous_total_ns=stats[live_sbs.TOTAL_NS],previous_depth_ns=stats[live_sbs.DEPTH_NS],
            previous_stereo_ns=stats[live_sbs.STEREO_NS],previous_background_ns=stats[live_sbs.BACKGROUND_NS],
            capture_ns=stats[live_sbs.INPUT_COPY_NS],vda_single_skip=options.get('vda_single_skip'),
            single_skip_reason=original_reason(*values,**alternate)))
        seen+=1;previous_decision=now
        return reason
    try:
        with ExitStack() as scope:
            scope.enter_context(patch.object(live_policy,'resolve_live',resolve))
            if history_policy is not None:
                scope.enter_context(patch.dict(os.environ,{'DEPTHSBS_DEPTH_HISTORY':history_policy}))
            if history_trace is not None:
                scope.enter_context(patch.object(live_sbs,'reset_reason',trace_reason))
            return live_sbs.sbs_worker(*args,**kwargs)
    finally:
        if history_trace is not None:
            (Path(history_trace)/f'{os.getpid()}.json').write_text(json.dumps(dict(
                background=background,history_policy=history_policy or os.environ.get('DEPTHSBS_DEPTH_HISTORY','continuous'),
                seen=seen,retained=len(samples),samples=list(samples)),indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--media',type=Path,required=True)
    parser.add_argument('--clip',action='append',choices=('lava','flower'))
    parser.add_argument('--windows',type=int,choices=(2,3),default=2)
    parser.add_argument('--normal-policy',action='store_true',help='Compare ordinary product policy to correction-off control')
    parser.add_argument('--model',choices=('ovda-small-c16','da2-base','da2-small','vda-small'),default='ovda-small-c16')
    parser.add_argument('--size',action='append',choices=('1080p','4k'))
    parser.add_argument('--trace-history',action='store_true',help='Bounded numeric capture/history metadata, no pixels')
    parser.add_argument('--history-policy',choices=('continuous','legacy','vda-single-skip'))
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    trace_directory=args.output/'history' if args.trace_history else None
    if trace_directory is not None:trace_directory.mkdir()
    from depthsbs_app import live_sbs
    from depthsbs_app.desktop import create_app
    from depthsbs_app.desktop_preferences import DesktopPreferences
    from PySide6.QtCore import QSettings
    from live_benchmark_source import SourceProcess
    import shiboken6
    app,engine,desktop=create_app(DesktopPreferences(QSettings(str((args.output/'preferences.ini').resolve()),QSettings.IniFormat)))
    live=desktop.live;live.setMode({'ovda-small-c16':'video-quality','vda-small':'video-quality','da2-base':'balanced','da2-small':'performance'}[args.model]);live.setLiveModel(args.model);live.setOvdaConfirmed(True)
    live.setStereoLayout('half-tb');live.setPresentationHz(0)
    live.output_placement.path=args.output/'placement.json'
    errors=[];live.errorOccurred.connect(errors.append)
    report=dict(rows=[],model=args.model,layout='half-tb',cap=0,vfg=False,
                history_policy=args.history_policy or os.environ.get('DEPTHSBS_DEPTH_HISTORY','continuous'),
                history_trace=bool(args.trace_history),
                source='user OLED clip: 64.0s lava, 65.2s flower; explicit SDR tone-mapped derivatives',
                fps_scope='distinct native output submissions, not display scans',media_hashes={})
    original=live_sbs.sbs_worker;source=None
    def save():(args.output/'report.json').write_text(json.dumps(report,indent=2))
    def pump(seconds):
        until=time.monotonic()+seconds
        while time.monotonic()<until:
            app.processEvents();time.sleep(.002)
            if errors:raise RuntimeError(errors[-1])
    def count():return live.native.report()['output']['submitted_frames'] if live.native is not None else 0
    def wait(predicate,seconds=90):
        until=time.monotonic()+seconds
        while not predicate() and time.monotonic()<until:pump(.02)
        if not predicate():raise TimeoutError(live.status)
    def stop():
        live.stop();wait(lambda:not live.active,20);pump(.1)
        result=live.native.report();assert result['live_pools']==result['live_nodes']==0
    try:
        for clip in (args.clip or ('lava','flower')):
            path=(args.media/(clip+'.mp4')).resolve(strict=True)
            report['media_hashes'][clip]=hashlib.sha256(path.read_bytes()).hexdigest()
            source=SourceProcess(path,interval_ms=16)
            for width,height in ({'1080p':(1920,1080),'4k':(3840,2160)}[size] for size in (args.size or ('1080p','4k'))):
                source.resize(round(width/source.devicePixelRatioF()),round(height/source.devicePixelRatioF()))
                source.request('activate');pump(.3)
                modes=(True,) if clip=='lava' else ((None,False,False,None) if args.normal_policy else (True,False,False,True))
                for background in modes:
                    live_sbs.sbs_worker=partial(worker,background,history_trace=trace_directory,history_policy=args.history_policy)
                    live.items=[dict(kind='window',id=int(source.winId()),pid=source.pid,label='Owned OLED scene reproduction',width=width,height=height)]
                    live.select(0);live.startMinimal();wait(lambda:count()>=5);pump(2)
                    rows=[]
                    for _ in range(args.windows):
                        before=live._stats();n0=count();source0=source.refresh()['sequence'];started=time.monotonic()
                        samples=[];last=None
                        while time.monotonic()-started<3:
                            pump(.02);current=live._stats()
                            if current[live_sbs.PROCESSED]!=last:
                                samples.append(current);last=current[live_sbs.PROCESSED]
                        after=live._stats();elapsed=time.monotonic()-started;n=after[live_sbs.PROCESSED]-before[live_sbs.PROCESSED]
                        def ms(index):
                            values=[s[index]/1e6 for s in samples]
                            return dict(median=statistics.median(values),mean=statistics.mean(values),max=max(values)) if values else None
                        rows.append(dict(fps=(count()-n0)/elapsed,source_fps=(source.refresh()['sequence']-source0)/elapsed,
                                         depth_ms=ms(live_sbs.DEPTH_NS),stereo_ms=ms(live_sbs.STEREO_NS),background_ms=ms(live_sbs.BACKGROUND_NS),
                                         h2d_bytes_per_processed=(after[live_sbs.H2D_BYTES]-before[live_sbs.H2D_BYTES])/max(1,n),
                                         d2h_bytes_per_processed=(after[live_sbs.D2H_BYTES]-before[live_sbs.D2H_BYTES])/max(1,n),
                                         reset_gap=after[live_sbs.RESET_GAP]-before[live_sbs.RESET_GAP],
                                         resets=after[live_sbs.RESETS]-before[live_sbs.RESETS],
                                         full_context_fraction=(after[live_sbs.OVDA_FULL_CONTEXT]-before[live_sbs.OVDA_FULL_CONTEXT])/max(1,n) if args.model=='ovda-small-c16' else None,
                                         measured_stat_samples=len(samples)))
                    row=dict(clip=clip,size=[width,height],background=background,windows=rows)
                    report['rows'].append(row);save();print(json.dumps(row),flush=True);stop()
            source.close();source=None
        report['completed']=True
    except BaseException as error:
        report['error']=repr(error);raise
    finally:
        if live.active:stop()
        if source is not None:source.close()
        live_sbs.sbs_worker=original;save();shiboken6.delete(engine)


if __name__=='__main__':main()
