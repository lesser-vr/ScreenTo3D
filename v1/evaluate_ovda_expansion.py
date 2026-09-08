"""Personal/non-commercial matched oVDA quality and whole-job benchmarks."""
import argparse
from contextlib import ExitStack
import csv
from dataclasses import replace
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import threading
import time
import uuid
from unittest.mock import patch

import cv2
import numpy as np
from evaluate_depth_models import inspect_media, sha

ROOT=Path(__file__).resolve().parents[1]
MEDIA=ROOT/'out/gpu-preview/DepthSBS-GPU-Preview/_internal/ffmpeg'
RUNTIME=Path('C:/TensorRT/TensorRT-11.2.1.2/bin')


def worker(args):
    import torch
    from depthsbs_app import pipeline, ovda, da2_base, trt_backend
    from depthsbs_app.depth_backend import resolve_backend, vda_binding
    from depthsbs_app.resources import configure_media_tools
    from depthsbs_app.local_projection import factory as projection
    from temporal_diagnostics import TemporalProbe
    configure_media_tools(MEDIA)
    torch.backends.cuda.matmul.allow_tf32=False
    torch.backends.cudnn.allow_tf32=False
    torch.cuda.reset_peak_memory_stats()
    probe=TemporalProbe()
    with ExitStack() as stack:
        stack.enter_context(os.add_dll_directory(str(RUNTIME)))
        if args.model=='small':
            stack.enter_context(patch.object(trt_backend,'_model_path',return_value=ROOT/'out/models/da2-small/model_fp16.onnx'))
            backend=resolve_backend('da2-small',trt_backend.DepthEngine,pipeline.preprocess)
        elif args.model=='base': backend=da2_base.binding(ROOT/'out/da2-base-local',RUNTIME)
        elif args.model=='vda': backend=vda_binding(ROOT/'out/vda-local',RUNTIME)
        else: backend=ovda.binding(ROOT/'out/ovda-local',RUNTIME,True)
        if args.quality:
            original=pipeline.StereoSynthesizer.render
            def render(renderer,frame,depth):
                probe.add(frame,depth,cut=renderer.is_scene_cut(frame))
                return original(renderer,frame,depth)
            stack.enter_context(patch.object(pipeline.StereoSynthesizer,'render',render))
        memory_before=torch.cuda.mem_get_info()[0]
        start=time.perf_counter()
        result=pipeline.convert_video(args.input,args.output,'video-quality',lambda e:None,
            depth_backend=backend, diagnostic_hashes=args.quality,
            projection_factory=projection if args.renderer=='cuda' else None,
            output_codec=args.codec)
        result['worker_job_seconds']=time.perf_counter()-start
        result['torch_peak_allocated_bytes']=torch.cuda.max_memory_allocated()
        result['device_free_bytes_before_after']=[memory_before,torch.cuda.mem_get_info()[0]]
        result['memory_note']='Torch peak excludes native TRT/NVENC; free-memory observations are device-wide, not a leak proof'
        if args.quality: result['temporal']=probe.report()
        result['input_sha256']=sha(args.input)
        result['source_hashes']={p:sha(ROOT/p) for p in ('v1/evaluate_ovda_expansion.py',
            'v1/depthsbs_app/pipeline.py','v1/depthsbs_app/stereo.py','v1/depthsbs_app/ovda.py',
            'experiments/ovda/trt_engine.py','experiments/ovda/oracle.py','experiments/ovda/preprocessing.py',
            'v1/depthsbs_app/local_projection.py','v1/depthsbs_app/config.py','v1/cuda_projection_experiment.py')}
        args.output.with_suffix('.json').write_text(json.dumps(result,indent=2),encoding='utf-8')


def run(root,source,name,model,renderer,quality=False,codec='h264'):
    output=root/f'{name}.mp4'
    command=[sys.executable,str(Path(__file__).resolve()),'--worker','--input',str(source),
             '--output',str(output),'--model',model,'--renderer',renderer,'--codec',codec]
    if quality: command+=['--quality']
    start=time.perf_counter()
    rows=[]; stop=threading.Event()
    def monitor():
        while not stop.is_set():
            query=subprocess.run(['nvidia-smi','--query-gpu=timestamp,memory.used,utilization.gpu,utilization.encoder,utilization.decoder,power.draw,clocks.sm','--format=csv,noheader,nounits'],capture_output=True,text=True)
            rows.append(dict(seconds=time.perf_counter()-start,returncode=query.returncode,value=query.stdout.strip(),error=query.stderr.strip()))
            stop.wait(.5)
    observer=threading.Thread(target=monitor); observer.start()
    try:
        with output.with_suffix('.log').open('w',encoding='utf-8') as log:
            subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
    finally:
        stop.set(); observer.join()
        output.with_suffix('.gpu.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    result=json.loads(output.with_suffix('.json').read_text(encoding='utf-8'))
    result['process_wall_seconds']=time.perf_counter()-start
    result['command']=command
    from depthsbs_app.pipeline import probe_video
    metadata=probe_video(source, output_codec=codec)
    inspect_media(output,metadata)
    output.with_suffix('.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('PASS',name,flush=True)
    return result


def review(root,source,names):
    from vda_comparison import inspection_sheet
    captures=[cv2.VideoCapture(str(root/f'{name}.mp4')) for name in names]
    writer=None
    try:
        for index in range(124):
            reads=[cap.read() for cap in captures]
            if not all(ok for ok,_ in reads):
                assert not any(ok for ok,_ in reads)
                break
            frames=[f for _,f in reads];h,w=frames[0].shape[:2];w//=2
            sheet=inspection_sheet(list(zip(names,frames)),w,h,lower=True)
            sheet=cv2.resize(sheet,(1000,round(sheet.shape[0]*1000/sheet.shape[1])//2*2))
            if writer is None:
                writer=cv2.VideoWriter(str(root/'hands-review-source.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),24,(sheet.shape[1],sheet.shape[0]))
                assert writer.isOpened()
            writer.write(sheet)
            if index in (30,60,90): assert cv2.imwrite(str(root/f'hands-{index}.jpg'),sheet)
    finally:
        for cap in captures: cap.release()
        if writer is not None: writer.release()
    subprocess.run([str(MEDIA/'ffmpeg.exe'),'-hide_banner','-loglevel','error','-nostdin','-i',str(root/'hands-review-source.mp4'),
                    '-c:v','libx264','-crf','18','-pix_fmt','yuv420p',str(root/'hands-review.mp4')],check=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--worker',action='store_true')
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--model',choices=('small','base','vda','ovda'),default='ovda')
    parser.add_argument('--renderer',choices=('cpu','cuda'),default='cpu')
    parser.add_argument('--codec',choices=('h264','hevc'),default='h264')
    parser.add_argument('--quality',action='store_true')
    parser.add_argument('--benchmark-only',action='store_true')
    args=parser.parse_args()
    if args.worker: worker(args); return
    from depthsbs_app.resources import configure_media_tools
    configure_media_tools(MEDIA)
    root=ROOT/'out/ovda-expansion-evaluation'/uuid.uuid4().hex;root.mkdir(parents=True)
    print(root,flush=True)
    report=dict(passed=False,quality={},benchmark={},environment=dict(os=platform.platform(),python=sys.version,
        git=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        dirty=subprocess.check_output(['git','status','--porcelain'],text=True),
        gpu=subprocess.check_output(['nvidia-smi','--query-gpu=name,driver_version,memory.total,pstate,power.limit','--format=csv'],text=True),
        ffmpeg=subprocess.check_output([str(MEDIA/'ffmpeg.exe'),'-version'],text=True).splitlines()[0],
        packages={name:importlib.metadata.version(name) for name in ('torch','tensorrt','numpy','opencv-python')},
        gpu_processes=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,process_name,used_memory','--format=csv'],text=True),
        note='No reboot; sequential test GPU jobs, desktop may compete; source Python runtime, no release build claim'))
    try:
        for model in (() if args.benchmark_only else ('small','base','vda','ovda')):
            report['quality'][model]=run(root,args.input,f'quality-{model}',model,'cpu',True)
        if not args.benchmark_only:
            gpu=run(root,args.input,'quality-ovda-cuda','ovda','cuda',True)
            cpu=report['quality']['ovda']
            assert gpu['telemetry']['diagnostic_hashes']==cpu['telemetry']['diagnostic_hashes']
            assert len({r['telemetry']['diagnostic_hashes']['decoded_rgb'] for r in report['quality'].values()})==1
            report['gpu_hash_parity']=True
            review(root,args.input,[f'quality-{m}' for m in ('small','base','vda','ovda')])
        for renderer in ('cpu','cuda'):
            runs=[]
            for index in range(6): runs.append(run(root,args.input,f'benchmark-{renderer}-{index}','ovda',renderer))
            fps=[r['processing_fps'] for r in runs[1:]]
            report['benchmark'][renderer]=dict(warmup_discarded=True,runs=runs,median_fps=statistics.median(fps),min_fps=min(fps),max_fps=max(fps))
        with (root/'benchmark.csv').open('w',newline='',encoding='utf-8') as stream:
            writer=csv.writer(stream);writer.writerow(['renderer','run','warmup','frames','pipeline_fps','process_wall_seconds','torch_peak_bytes'])
            for renderer,group in report['benchmark'].items():
                for i,row in enumerate(group['runs']):writer.writerow([renderer,i,i==0,row['frames'],row['processing_fps'],row['process_wall_seconds'],row['torch_peak_allocated_bytes']])
        report['passed']=True
    finally:
        (root/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(root/'report.json',flush=True)


if __name__=='__main__':main()
