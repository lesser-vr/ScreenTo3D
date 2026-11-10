"""Matched native frame-ID/age sampling with an owned public source."""
import argparse
from collections import deque
from contextlib import nullcontext
import json
import os
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'v1'))
from trial import installed,worker

def main():
    import faulthandler
    faulthandler.enable();faulthandler.dump_traceback_later(120,repeat=True)
    p=argparse.ArgumentParser();p.add_argument('--model',choices=['small','base','zipdepth'],required=True)
    p.add_argument('--clip',choices=['Jockey','Beauty'],help='Genuine public 4K120 source through owned mpv')
    p.add_argument('--tag',default='hfr',help='Evidence suffix for a fresh HFR run')
    p.add_argument('--cap',type=int,choices=[0,30,60],default=0)
    p.add_argument('--quality',choices=['detail','budget','reference'],default='detail')
    p.add_argument('--repeats',type=int,choices=range(1,11),default=3)
    p.add_argument('--baseline',action='store_true',help='Pinned pre-optimization worker and output-only pacing')
    p.add_argument('--guide-baseline',action='store_true',help='Prior bitmap/paced product with double guide')
    p.add_argument('--reduced-guide',action='store_true',help='Benchmark the pinned 3:2 DA2 guide')
    p.add_argument('--timing-trace',action='store_true',help='Bounded worker-ready and GUI publication timestamps')
    p.add_argument('--pacing',choices=('production','relative','phase','phase3','work-phase3','work-guard3'),default='production',help='Product policy or explicit benchmark-only baseline/candidate')
    p.add_argument('--event-loop',choices=('pump','qt'),default='pump',help='Manual historical harness or actual Qt event loop')
    a=p.parse_args()
    if a.reduced_guide and (a.model=='zipdepth' or a.baseline or a.guide_baseline or a.timing_trace or a.pacing!='production'):
        p.error('Reduced guide requires a DA2 model with production pacing')
    if a.model == 'base' and (a.baseline or a.guide_baseline or a.timing_trace or a.pacing != 'production'):
        p.error('Base measurements use the production worker and pacing')
    if a.baseline and a.guide_baseline:p.error('Choose one baseline')
    out=ROOT/(f'out/public-hfr/{a.clip}-{a.model}-{a.tag}.json' if a.clip else f'out/zipdepth-latency-{a.model}.json')
    if out.exists():raise FileExistsError(out)
    os.environ['DEPTHSBS_GPU_CAPTURE']='1'
    os.environ['DEPTHSBS_STEREO_RENDERER']='cuda'
    os.environ['DEPTHSBS_STEREO_QUALITY']=a.quality
    with installed() if a.model=='zipdepth' else nullcontext():
        from depthsbs_app import desktop,live_sbs
        from depthsbs_app.output_placement import OutputPlacement
        from live_benchmark_source import SourceProcess
        from PySide6.QtCore import Qt
        import numpy as np
        import shiboken6
        if a.model=='zipdepth':live_sbs.sbs_worker=worker
        if a.reduced_guide:
            from compare_guide_resolution import native_worker
            live_sbs.sbs_worker=native_worker
        if a.baseline:
            from gpu_load_baseline import worker as baseline_worker
            live_sbs.sbs_worker=baseline_worker
        if a.guide_baseline:
            from gpu_load_baseline import guide_worker
            live_sbs.sbs_worker=guide_worker
        if a.timing_trace:
            if a.baseline or a.guide_baseline:p.error('Timing trace uses current artifacts')
            from pacing_probe import worker as traced_worker
            os.environ['DEPTHSBS_TIMING_TRACE']=str(out.with_suffix('.worker.json'))
            os.environ['DEPTHSBS_TIMING_MODEL']=a.model
            live_sbs.sbs_worker=traced_worker
        if a.pacing!='production':
            if a.baseline or a.guide_baseline:p.error('Pacing candidate uses current artifacts')
            from pacing_candidate import DELIVERY,polling_wakeup_type,worker as pacing_worker
            from depthsbs_app import live_preview
            live_preview.delivery_cadence=lambda hz,**kwargs: DELIVERY[a.pacing](hz)
            live_preview.FrameWakeup=polling_wakeup_type()
            os.environ['DEPTHSBS_PACING_CANDIDATE']=a.pacing
            os.environ['DEPTHSBS_PACING_MODEL']=a.model
            os.environ['DEPTHSBS_PACING_TRACE']='1' if a.timing_trace else '0'
            live_sbs.sbs_worker=pacing_worker
        app,qml,controller=desktop.create_app();live=controller.live
        live.output_placement=OutputPlacement(ROOT/f'out/zipdepth-latency-placement-{a.model}.json')
        live.setMode('balanced' if a.model == 'base' else 'performance');live.setProcessingPath('gpu-texture')
        live.setPresentationHz(a.cap)
        samples=deque(maxlen=8192);errors=[];last=[0];source=None
        report=dict(completed=False,model=a.model,source_timer_ms=None if a.clip else 8,strength=live.strength,
                    shape=[2160,7680],vfg=False,cap=a.cap,quality=a.quality,pacing=a.pacing,event_loop=a.event_loop,baseline=a.baseline,guide_baseline=a.guide_baseline,reduced_guide=a.reduced_guide,rows=[],errors=errors,
                    age_scope='WGC source timestamp to distinct Qt afterFrameEnd; capture callback age also reported. Not physical display latency.')
        live.errorOccurred.connect(errors.append)
        def pump(seconds):
            if a.event_loop=='qt':
                from PySide6.QtCore import QEventLoop,QTimer
                loop=QEventLoop()
                timer=QTimer();timer.setTimerType(Qt.PreciseTimer);timer.setSingleShot(True)
                timer.timeout.connect(loop.quit)
                timer.start(max(1,round(seconds*1000)))
                loop.exec()
                return
            end=time.monotonic()+seconds
            while time.monotonic()<end:
                app.processEvents();time.sleep(.001)
        def wait(predicate):
            end=time.monotonic()+90
            while not predicate():
                pump(.02)
                if errors:raise RuntimeError(errors[-1])
                if time.monotonic()>end:raise TimeoutError(live.status)
        def on_frame():
            if live.native is None:return
            seq=live.native.report()['output']['last_submitted_id']
            if not seq or seq==last[0]:return
            last[0]=seq
            frame=next((f for f in tuple(live.native.frames.values()) if f.sequence==seq),None)
            if frame:samples.append((time.perf_counter_ns(),seq,frame.source_ns,frame.callback_ns))
        try:
            if a.clip:
                print('Opening owned HFR source',flush=True)
                from hfr_source import Source
                source=Source(a.clip,out.with_suffix('.player.log'))
                print('Owned HFR source ready',flush=True)
                live.items=[source.source]
                report['source']=dict(clip=a.clip,sha256=source.sha256,probe=source.probe,command=source.command)
            else:
                source=SourceProcess('FloorballGame',interval_ms=8)
                source.resize(round(3840/source.devicePixelRatioF()),round(2160/source.devicePixelRatioF()))
                source.request('activate');pump(.4)
                live.items=[dict(kind='window',id=int(source.winId()),pid=source.pid,label='Owned ZipDepth latency',width=3840,height=2160)]
            live.select(0);live.startMinimal()
            print('SBS start requested',flush=True)
            wait(lambda:live.native is not None and live.native.report()['output']['submitted_frames']>=10)
            live.output_window.afterFrameEnd.connect(on_frame,Qt.DirectConnection)
            publications=deque(maxlen=16384)
            if a.timing_trace:
                original_consume=live.native.consume
                def traced_consume(*args,**kwargs):
                    before=live.native.last_sequence
                    changed=original_consume(*args,**kwargs)
                    if live.native.last_sequence!=before:
                        publications.append((live.native.last_sequence,time.perf_counter_ns()))
                    return changed
                live.native.consume=traced_consume
            pump(3)
            for repeat in range(a.repeats):
                begin=time.perf_counter_ns();before=live.native.report()['output']['submitted_frames']
                processed=live._stats()[0]
                received=live.report()['received']
                polls=live.poll_count; cpu=time.process_time()
                pump(10)
                end=time.perf_counter_ns()
                if errors or not live.active:raise RuntimeError(str(errors) + live.status)
                rows=[s for s in tuple(samples) if begin<s[0]<=end]
                stamps=np.array([r[0] for r in rows],dtype=np.float64)
                age=np.array([(r[0]-r[2])/1e6 for r in rows]); callback=np.array([(r[0]-r[3])/1e6 for r in rows])
                if len(rows)<10:raise ValueError('Insufficient native age samples')
                elapsed=(end-begin)/1e9
                submitted=live.native.report()['output']['submitted_frames']-before
                report['rows'].append(dict(repeat=repeat,output_fps=submitted/elapsed,processed_fps=(live._stats()[0]-processed)/elapsed,
                    gui_cpu_percent=(time.process_time()-cpu)/elapsed*100,
                    delivery_polls_per_sec=(live.poll_count-polls)/elapsed,
                    begin_ns=begin,end_ns=end,
                    received_fps=(live.report()['received']-received)/elapsed,
                    age_samples=len(rows),sample_coverage=len(rows)/submitted,
                    source_age_p50_ms=float(np.median(age)),source_age_p95_ms=float(np.percentile(age,95)),
                    callback_age_p50_ms=float(np.median(callback)),callback_age_p95_ms=float(np.percentile(callback,95)),
                    interval_p95_ms=float(np.percentile(np.diff(stamps)/1e6,95))))
                print(json.dumps(report['rows'][-1]),flush=True)
            report['last_report']=live.report()
            assert report['last_report']['gpu_stage_timing_available']==(a.model=='small')
            assert (report['last_report']['gpu_stage_ms'] is None)==(a.model!='small')
            if a.clip:
                assert (report['last_report']['width'],report['last_report']['height'])==(7680,2160)
                assert live.native.pool.width==7680 and live.native.pool.height==2160
            live.stop();wait(lambda:not live.active)
            report['cleanup']=live.native.report()
            if a.timing_trace:
                report['timing_trace']=dict(publications=list(publications),outputs=list(samples))
            assert report['cleanup']['live_pools']==report['cleanup']['live_nodes']==0
            report['completed']=True
        except BaseException as exc:
            report['error']=repr(exc);raise
        finally:
            if live.active:live.stop();wait(lambda:not live.active)
            if source is not None:source.close()
            out.write_text(json.dumps(report,indent=2),encoding='utf-8')
            shiboken6.delete(qml)
            faulthandler.cancel_dump_traceback_later()

if __name__=='__main__':main()
