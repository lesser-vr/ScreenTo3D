"""Whole-GPU telemetry aligned to the existing owned 4K120 native benchmark."""
import argparse
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[2]
FIELDS=['utilization.gpu','utilization.memory','utilization.decoder','memory.used',
        'power.draw','clocks.current.sm','clocks.current.memory','temperature.gpu']

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--tag',default='gpu-20261106')
    parser.add_argument('--model',choices=['small','base','zipdepth','both'],default='both')
    parser.add_argument('--cap',type=int,choices=[0,30,60],default=0)
    parser.add_argument('--quality',choices=['detail','budget','reference'],default='detail')
    parser.add_argument('--player-baseline',action='store_true')
    parser.add_argument('--repeats',type=int,choices=range(1,11),default=3)
    parser.add_argument('--baseline',action='store_true')
    parser.add_argument('--guide-baseline',action='store_true')
    parser.add_argument('--reduced-guide',action='store_true')
    parser.add_argument('--pacing',choices=('production','relative','phase','phase3','work-phase3','work-guard3'),default='production')
    parser.add_argument('--event-loop',choices=('pump','qt'),default='pump')
    args=parser.parse_args()
    if args.baseline and args.guide_baseline:parser.error('Choose one baseline')
    out=ROOT/'out/public-hfr'/f'{args.tag}.json'
    if out.exists():raise FileExistsError(out)
    smi=shutil.which('nvidia-smi')
    report=dict(completed=False,scope='Whole GPU including public player, desktop and other apps; not per-process usage.',
                sample_period_ms=200,fields=FIELDS,cases=[],samples=[])
    report['device']=subprocess.check_output([smi,'--id=0','--query-gpu=name,driver_version,memory.total,power.limit',
        '--format=csv,noheader,nounits'],creationflags=subprocess.CREATE_NO_WINDOW,text=True).strip()
    def summarize(samples):
        assert samples
        result=dict(count=len(samples))
        for key in FIELDS:
            values=[s[key] for s in samples]
            result[key]=dict(mean=statistics.mean(values),median=statistics.median(values),min=min(values),max=max(values))
        return result
    telemetry=subprocess.Popen([smi,'--id=0','--query-gpu='+','.join(FIELDS),'--format=csv,noheader,nounits','-lms','200'],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,creationflags=subprocess.CREATE_NO_WINDOW)
    def collect():
        for line in telemetry.stdout:
            try:values=[float(v.strip()) for v in line.split(',')]
            except ValueError:continue
            if len(values)==len(FIELDS):report['samples'].append(dict(ns=time.perf_counter_ns(),**dict(zip(FIELDS,values))))
    reader=threading.Thread(target=collect,daemon=True);reader.start()
    child=None
    try:
        start=time.perf_counter_ns();time.sleep(5);end=time.perf_counter_ns()
        report['baseline']=summarize([s for s in report['samples'] if start<=s['ns']<=end])
        if args.player_baseline:
            from hfr_source import Source
            source=Source('Jockey',out.with_suffix('.player.log'))
            try:
                start=time.perf_counter_ns();time.sleep(10);end=time.perf_counter_ns()
                report['player_only']=summarize([s for s in report['samples'] if start<=s['ns']<=end])
            finally:source.close()
        env=dict(os.environ,PYTHONPATH='v1;experiments/zipdepth;out/gui-python-deps;out/capture-python-deps;out/v1-python-deps')
        for model in (('small','zipdepth') if args.model=='both' else (args.model,)):
            target=ROOT/'out/public-hfr'/f'Jockey-{model}-{args.tag}.json'
            if target.exists():raise FileExistsError(target)
            with target.with_suffix('.run.log').open('wb') as log:
                child=subprocess.Popen([sys.executable,str(ROOT/'experiments/zipdepth/latency.py'),
                    '--model',model,'--clip','Jockey','--tag',args.tag,'--cap',str(args.cap),'--quality',args.quality,
                    '--repeats',str(args.repeats),'--pacing',args.pacing,'--event-loop',args.event_loop]+(['--baseline'] if args.baseline else [])+
                    (['--guide-baseline'] if args.guide_baseline else [])+
                    (['--reduced-guide'] if args.reduced_guide else []),cwd=ROOT,env=env,
                    stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
                code=child.wait(timeout=180)
                if code:raise RuntimeError(f'{model} benchmark failed: {code}; see {log.name}')
            child=None
            benchmark=json.loads(target.read_text(encoding='utf-8'))
            assert benchmark['completed'] and not benchmark['errors']
            intervals=benchmark['rows']
            matched=[s for s in report['samples'] if any(r['begin_ns']<=s['ns']<=r['end_ns'] for r in intervals)]
            case=dict(model=model,cap=args.cap,quality=args.quality,benchmark=str(target),telemetry=summarize(matched),
                output_fps=statistics.median(r['output_fps'] for r in intervals),
                received_fps=statistics.median(r['received_fps'] for r in intervals))
            report['cases'].append(case)
            print(json.dumps(case),flush=True)
        report['completed']=True
    except BaseException as exc:
        report['error']=repr(exc);raise
    finally:
        if child is not None and child.poll() is None:
            subprocess.run(['taskkill','/PID',str(child.pid),'/T','/F'],capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        telemetry.terminate();telemetry.wait(timeout=5);reader.join(timeout=5)
        out.write_text(json.dumps(report,indent=2),encoding='utf-8')

if __name__=='__main__':main()
