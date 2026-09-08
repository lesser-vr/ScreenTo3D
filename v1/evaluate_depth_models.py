"""Sequential isolated-process model/precision evaluation on one short clip."""
import argparse
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
import uuid
from unittest.mock import patch

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
VARIANTS = ('small','base','vda','fp16','fp16-head')
CANDIDATES = {'fp16':'c2fab6ca37cc4d1ab5c4f3458b3e2127', 'fp16-head':'a8e14fb567f243029c101091043e18b1'}


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()


def run_one(args):
    import torch
    from depthsbs_app import pipeline, da2_base
    from depthsbs_app.resources import configure_media_tools
    from depthsbs_app.depth_backend import resolve_backend, vda_binding
    from vda_comparison import BoundedEngine
    configure_media_tools(ROOT/'out/gpu-preview/DepthSBS-GPU-Preview/_internal/ffmpeg')
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.cuda.reset_peak_memory_stats()
    with os.add_dll_directory('C:/TensorRT/TensorRT-11.2.1.2/bin'):
        runtime=Path('C:/TensorRT/TensorRT-11.2.1.2/bin')
        if args.one == 'small':
            from depthsbs_app import trt_backend
            def factory(progress):
                with patch.object(trt_backend,'_model_path',return_value=ROOT/'out/models/da2-small/model_fp16.onnx'):
                    return trt_backend.DepthEngine(progress)
            backend=resolve_backend('da2-small',factory,pipeline.preprocess)
        elif args.one == 'vda':
            backend=vda_binding(ROOT/'out/vda-local',runtime)
        elif args.one == 'base':
            backend=da2_base.binding(ROOT/'out/da2-base-local',runtime)
        else:
            # Diagnostic-only execution of our own failed candidates, never public registration.
            directory=ROOT/'out/da2-base-trt'/CANDIDATES[args.one]
            candidate=json.loads((directory/'report.json').read_text())
            assert candidate['input_shape']==[1,3,518,896] and candidate['precision']==args.one
            assert sha(directory/'model.plan')==candidate['plan_sha256']
            da2_base.PROFILES={(518,896):(candidate['plan_sha256'],(directory/'model.plan').stat().st_size)}
            backend=da2_base.binding(directory,runtime)
            backend=replace(backend,spec=replace(backend.spec,runtime='tensorrt-'+args.one+'-rejected-candidate'))
        factory=backend.engine_factory
        memory={}
        def measured_factory(progress):
            if args.memory:
                torch.cuda.synchronize()
                memory['free_before_engine']=torch.cuda.mem_get_info()[0]
            owned=factory(progress)
            if args.memory:
                torch.cuda.synchronize()
                memory['free_after_engine']=torch.cuda.mem_get_info()[0]
                original_telemetry=owned.telemetry
                def telemetry():
                    torch.cuda.synchronize()
                    memory['free_after_frames']=torch.cuda.mem_get_info()[0]
                    return original_telemetry()
                owned.telemetry=telemetry
            return BoundedEngine(owned,124)
        backend=replace(backend,engine_factory=measured_factory)
        depth_stats=[]
        original_render=pipeline.StereoSynthesizer.render
        previous=[None]
        def diagnostic_render(renderer, frame, depth):
            resized=cv2.resize(depth[0],(frame.shape[1],frame.shape[0]),interpolation=cv2.INTER_CUBIC)
            low,high=np.percentile(resized,[5,95])
            normalized=np.clip((resized-low)/max(high-low,1e-6),0,1)
            if previous[0] is not None:
                old_rgb,old_depth=previous[0]
                stable=np.max(np.abs(frame.astype(np.int16)-old_rgb.astype(np.int16)),axis=2)<=2
                stable=cv2.erode(stable.astype(np.uint8),np.ones((9,9),np.uint8)).astype(bool)
                delta=np.abs(normalized-old_depth)[stable]
                depth_stats.append(dict(static_fraction=float(stable.mean()),mae=float(delta.mean()) if delta.size else None))
            previous[0]=(frame.copy(),normalized.copy())
            return original_render(renderer,frame,depth)
        start=time.perf_counter()
        with patch.object(pipeline.StereoSynthesizer,'render',diagnostic_render if args.hashes else original_render):
            result=pipeline.convert_video(args.input,args.output,'video-quality',lambda event:None,
                depth_backend=backend,diagnostic_hashes=args.hashes)
        result['wall_seconds']=time.perf_counter()-start
        if args.hashes:
            result['raw_depth_static_pixel_changes']=depth_stats
            result['depth_metric_note']='Per-frame 5/95 normalized raw depth before renderer EMA, color-static eroded mask; no optical flow or ground truth'
        result['torch_peak_bytes']=torch.cuda.max_memory_allocated()
        if args.memory:
            memory['engine_delta_bytes']=memory['free_before_engine']-memory['free_after_engine']
            memory['active_delta_bytes']=memory['free_before_engine']-memory['free_after_frames']
            memory['note']='Device-wide free-memory deltas, includes native TRT and allocator reservations; sampled, not peak or process-isolated proof'
            result['memory_probe']=memory
        result['memory_note']='PyTorch allocations only; TensorRT native engine/workspace allocations excluded'
        args.output.with_suffix('.json').write_text(json.dumps(result,indent=2))


def inspect_media(path, expected):
    ffprobe=ROOT/'out/gpu-preview/DepthSBS-GPU-Preview/_internal/ffmpeg/ffprobe.exe'
    streams=json.loads(subprocess.check_output([str(ffprobe),'-v','error','-show_streams','-of','json',str(path)]))['streams']
    assert any(s['codec_type']=='audio' for s in streams)==expected['has_audio']
    capture=cv2.VideoCapture(str(path)); count=0
    try:
        while True:
            ok,frame=capture.read()
            if not ok: break
            assert frame.shape==(expected['height'],2*expected['width'],3)
            count+=1
    finally: capture.release()
    assert count==expected['total_frames']


def review(root, source, metadata):
    from vda_comparison import inspection_sheet
    names=('small','base','vda')
    captures=[cv2.VideoCapture(str(p)) for p in (source,*(root/f'{name}-quality.mp4' for name in names))]
    prior=None
    stats={name:dict(stable_sum=0.,stable_values=0,far_background_artifact_pixels=0,far_background_pixels=0) for name in names}
    writer=None
    try:
        for index in range(metadata['total_frames']):
            reads=[c.read() for c in captures]
            assert all(ok for ok,_ in reads)
            original,*outputs=[f for _,f in reads]
            h,w=original.shape[:2]
            rows=[('SOURCE duplicated',np.concatenate([original,original],axis=1)),
                  *[(name+' - left / right',f) for name,f in zip(names,outputs)]]
            sheet=inspection_sheet(rows,w,h,lower=True)
            if index in (20,metadata['total_frames']//2,100):
                assert cv2.imwrite(str(root/f'hands-{index}.png'),sheet)
            # Labeled synchronized motion artifact; retain original model videos with audio.
            if writer is None:
                writer=cv2.VideoWriter(str(root/'hand-motion.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),metadata['fps'],(sheet.shape[1],sheet.shape[0]))
                if not writer.isOpened(): raise RuntimeError('Review writer failed')
            writer.write(sheet)
            green=(original[:,:,1]>200)&(original[:,:,0]<45)&(original[:,:,2]<45)
            far=cv2.erode(green.astype(np.uint8),np.ones((41,41),np.uint8)).astype(bool)
            if prior is not None:
                old_source,old_outputs=prior
                stable=(np.max(np.abs(original.astype(np.int16)-old_source.astype(np.int16)),axis=2)<=2)&far
                stable=cv2.erode(stable.astype(np.uint8),np.ones((9,9),np.uint8)).astype(bool)
            for name,output in zip(names,outputs):
                for eye in (output[:,:w],output[:,w:]):
                    not_green=(eye[:,:,1]<160)|(eye[:,:,0]>70)|(eye[:,:,2]>70)
                    stats[name]['far_background_artifact_pixels']+=int(np.count_nonzero(not_green&far))
                    stats[name]['far_background_pixels']+=int(far.sum())
                if prior is not None:
                    previous=old_outputs[names.index(name)]
                    mask=np.concatenate([stable,stable],axis=1)
                    delta=np.abs(output.astype(np.int16)-previous.astype(np.int16))[mask]
                    stats[name]['stable_sum']+=float(delta.sum())
                    stats[name]['stable_values']+=delta.size
            prior=(original,outputs)
        assert not any(c.read()[0] for c in captures)
    finally:
        for c in captures:c.release()
        if writer is not None:writer.release()
    for record in stats.values():
        record['stable_background_temporal_mae_255']=record['stable_sum']/max(1,record['stable_values'])
        record['far_background_artifact_fraction']=record['far_background_artifact_pixels']/max(1,record['far_background_pixels'])
    return stats


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--one',choices=VARIANTS)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--hashes',action='store_true')
    parser.add_argument('--memory',action='store_true')
    args=parser.parse_args()
    if args.one:
        run_one(args);return
    from depthsbs_app import pipeline
    from depthsbs_app.resources import configure_media_tools
    from vda_comparison import validate_metadata, validate_runs
    configure_media_tools(ROOT/'out/gpu-preview/DepthSBS-GPU-Preview/_internal/ffmpeg')
    metadata=pipeline.probe_video(args.input);validate_metadata(metadata,124)
    root=ROOT/'out/model-evaluation'/uuid.uuid4().hex;root.mkdir(parents=True)
    print(root,flush=True)
    report=dict(passed=False,metadata=metadata,input_sha256=sha(args.input),runs={},quality={},
        os=platform.platform(),git_head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        git_dirty=bool(subprocess.check_output(['git','status','--porcelain'],text=True).strip()),
        note='Short exploratory whole-pipeline timings; one warmup plus five measured runs per isolated process variant. No sustained target claim.',
        quality_note='Static green background temporal MAE and far-background contamination are limited proxies; no ground truth depth, blinded A/B or VR assessment.')
    report['gpu_before']=subprocess.check_output(['nvidia-smi','--query-gpu=name,driver_version,memory.total,memory.used,utilization.gpu,power.draw,clocks.sm','--format=csv'],text=True)
    try:
        for repetition in range(6):
            for name in VARIANTS:
                path=root/f'{name}-{repetition}.mp4'
                command=[sys.executable,__file__,'--input',str(args.input),'--one',name,'--output',str(path)]
                with (root/f'{name}-{repetition}.log').open('w') as log:
                    subprocess.run(command,check=True,stdout=log,stderr=subprocess.STDOUT)
                result=json.loads(path.with_suffix('.json').read_text())
                inspect_media(path,metadata)
                report['runs'].setdefault(name,[]).append(result)
                print(f'PASS: {name} run {repetition}'+(' warmup' if repetition==0 else ''),flush=True)
        for name in ('small','base','vda'):
            path=root/f'{name}-quality.mp4'
            subprocess.run([sys.executable,__file__,'--input',str(args.input),'--one',name,'--output',str(path),'--hashes'],check=True)
            report['quality'][name]=json.loads(path.with_suffix('.json').read_text())
            inspect_media(path,metadata)
        validate_runs(report['quality'],metadata['total_frames'],metadata['total_frames'])
        report['quality_proxies']=review(root,args.input,metadata)
        report['summary']={name:dict(median_fps=statistics.median([r['frames']/r['wall_seconds'] for r in rows[1:]]),
            min_fps=min(r['frames']/r['wall_seconds'] for r in rows[1:]),
            max_fps=max(r['frames']/r['wall_seconds'] for r in rows[1:]),
            torch_peak_bytes=max(r['torch_peak_bytes'] for r in rows[1:])) for name,rows in report['runs'].items()}
        assert sha(args.input)==report['input_sha256']
        report['passed']=True
    finally:
        report['gpu_after']=subprocess.check_output(['nvidia-smi','--query-gpu=name,memory.used,utilization.gpu,power.draw,clocks.sm','--format=csv'],text=True)
        (root/'report.json').write_text(json.dumps(report,indent=2))
        print(root/'report.json',flush=True)


if __name__=='__main__':main()
