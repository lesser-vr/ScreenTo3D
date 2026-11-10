# oVDA precision evaluation, NC-SA-UHDV1.0; see LICENSE/README.md.
"""Matched public-frame depth/cache/native-SBS comparisons, not visual acceptance."""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import statistics
import time
import cv2
import numpy as np
import torch

from trial_runtime import create_engine, PINS
from depthsbs_app.live_policy import resolve_live
from depthsbs_app.live_source_gpu_texture import LiveSourceGpuTexture
from public_test_media import CORPUS


class TimedContext:
    def __init__(self, owner):
        self.owner=owner
        self.context=owner.context
        self.start=torch.cuda.Event(enable_timing=True)
        self.end=torch.cuda.Event(enable_timing=True)
    def __getattr__(self,name):return getattr(self.context,name)
    def execute_async_v3(self,stream):
        self.start.record(self.owner.stream)
        result=self.context.execute_async_v3(stream)
        self.end.record(self.owner.stream)
        return result
    def elapsed(self):return self.start.elapsed_time(self.end)


def normalize(depth):
    lo,hi=np.percentile(depth,[2,98])
    return np.clip((depth-lo)/max(hi-lo,1e-6),0,1),max(float(hi-lo),1e-6)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--reference',choices=('fp32','fp32-current'),default='fp32')
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    report=dict(scope='matched depth and native texture readback; timing excludes capture/display and quality readbacks',
                gpu=torch.cuda.get_device_name(),reference=args.reference,sources={},phases=[],strict_tolerance=dict(atol=.001,rtol=.001))
    clips={}
    for name in ('FloorballGame','OfficeWalk','ParkingGarage'):
        path=CORPUS/(name+'.mp4')
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if digest!=json.loads(path.with_suffix('.json').read_text())['sha256']:
            raise ValueError('Public clip identity changed')
        cap=cv2.VideoCapture(str(path)); frames=[]
        try:
            for _ in range(48):
                ok,bgr=cap.read()
                if not ok:raise ValueError('Short public input')
                frames.append(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB))
        finally:cap.release()
        clips[name]=frames
        report['sources'][name]=digest
    variants=('fp32',*PINS)
    policy=replace(resolve_live('video-quality',.5),stereo_layout='full-sbs')
    try:
        for width,height,count in ((1280,720,48),(3440,1440,18),(1080,1920,18),(1024,1024,18),(3840,2160,18)):
            engines={};posts={}
            phase=dict(size=[width,height],canvas=[518,924],frames=0,results={})
            data={v:dict(engine_ms=[],infer_ms=[],raw_error_percent=[],temporal_error=[],sbs_mae=[],
                         sbs_fraction_gt8=[],strict_depth_failures=0,strict_cache_checks=[],previous=None) for v in variants}
            try:
                for variant in variants:
                    engine=create_engine(args.reference if variant=='fp32' else variant)
                    engine.context=TimedContext(engine)
                    engines[variant]=engine
                    posts[variant]=LiveSourceGpuTexture(width,height,policy,engine,diagnostic=True)
                index=0
                for clip,frames in clips.items():
                    for variant in variants:
                        engines[variant].reset('start' if index==0 else 'scene_cut')
                        posts[variant].reset()
                        data[variant]['previous']=None
                    for number,original in enumerate(frames[:count]):
                        frame=np.ascontiguousarray(cv2.resize(original,(width,height),interpolation=cv2.INTER_LINEAR))
                        rgb={};depth={};normal={}
                        for variant in variants:
                            engine,post=engines[variant],posts[variant]
                            started=time.perf_counter()
                            token=post.infer(frame)
                            data[variant]['infer_ms'].append((time.perf_counter()-started)*1000)
                            data[variant]['engine_ms'].append(engine.context.elapsed())
                            engine.stream.synchronize()  # Depth restoration is queued after TRT's own wait.
                            depth[variant]=token.tensor.cpu().numpy().copy()
                            normal[variant],scale=normalize(depth[variant])
                            post.slot=index%2
                            slot=post.render(frame,token)
                            output=np.empty((height,width*2,4),np.uint8)
                            post.pool.check(post.pool.dll.live_pool_readback(post.pool.handle,slot,output.ctypes.data))
                            if not np.all(output[:,:,3]==255):raise ValueError('Invalid alpha')
                            rgb[variant]=output[:,:,:3].copy()
                        scale=max(float(np.percentile(depth['fp32'],98)-np.percentile(depth['fp32'],2)),1e-6)
                        for variant in variants[1:]:
                            row=data[variant]
                            row['raw_error_percent'].append(float(np.abs(depth[variant]-depth['fp32']).mean())/scale*100)
                            row['strict_depth_failures']+=int(not np.allclose(depth[variant],depth['fp32'],atol=.001,rtol=.001))
                            if row['previous'] is not None:
                                delta=(normal[variant]-row['previous'])-(normal['fp32']-data['fp32']['previous'])
                                row['temporal_error'].append(float(np.abs(delta).mean()))
                            diff=np.abs(rgb[variant].astype(np.int16)-rgb['fp32'].astype(np.int16))
                            row['sbs_mae'].append(float(diff.mean()))
                            row['sbs_fraction_gt8'].append(float(np.mean(np.any(diff>8,axis=2))))
                            if number in (0,15,count-1):
                                row['strict_cache_checks'].append(dict(clip=clip,frame=number,
                                    passed=all(torch.allclose(engines[variant].cache[k],engines['fp32'].cache[k],atol=.001,rtol=.001)
                                               for k in engines['fp32'].cache)))
                        for variant in variants:data[variant]['previous']=normal[variant]
                        if number==count-1 and clip=='FloorballGame':
                            for variant in variants:
                                preview=cv2.resize(rgb[variant],(1280,round(height*1280/(width*2))))
                                cv2.imwrite(str(args.output/f'{width}x{height}-{variant}.png'),cv2.cvtColor(preview,cv2.COLOR_RGB2BGR))
                        index+=1
                phase['frames']=index
                for variant in variants:
                    row=data[variant];row.pop('previous')
                    summary={key:dict(mean=statistics.mean(values),max=max(values),median=statistics.median(values))
                             for key,values in row.items() if isinstance(values,list) and values and key!='strict_cache_checks'}
                    summary['strict_depth_failures']=row['strict_depth_failures']
                    summary['strict_cache_checks']=row['strict_cache_checks']
                    summary['used_cache_slots']=engines[variant].used
                    phase['results'][variant]=summary
                report['phases'].append(phase)
                (args.output/'report.json').write_text(json.dumps(report,indent=2))
                print(json.dumps(dict(size=phase['size'],frames=index,
                                      engine_ms={v:phase['results'][v]['engine_ms']['median'] for v in variants},
                                      sbs_mae={v:phase['results'][v]['sbs_mae']['mean'] for v in variants[1:]})),flush=True)
            finally:
                for post in posts.values():post.close()
                for engine in engines.values():
                    if isinstance(engine.context,TimedContext):engine.context=engine.context.context
                    engine.close()
        report['completed']=True
    finally:
        (args.output/'report.json').write_text(json.dumps(report,indent=2))


if __name__=='__main__':main()
