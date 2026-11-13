# oVDA temporal policy evaluation, NC-SA-UHDV1.0; see LICENSE/README.md.
"""Matched public frames: dense timeline, strict dropped timeline, retained timeline.

Dense oVDA is a comparison reference, not depth ground truth. This deliberately
changes the history on dropped captures; numerical parity applies only to the
separate consecutive-input phase.
"""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import statistics
import cv2
import numpy as np
import torch
from screento3d_app import ovda
from screento3d_app.desktop_jobs import ROOT
from screento3d_app.gpu_frame import GpuFrame
from screento3d_app.live_policy import resolve_live
from screento3d_app.live_sbs import reset_reason
from screento3d_app.live_source_gpu_texture import LiveSourceGpuTexture
from screento3d_app.ovda_geometry import select_profile
from screento3d_app.stereo_layout import dimensions
from public_test_media import CORPUS


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    cls=ovda.runtime_class(True)
    profiles=ovda.profiles(ROOT/'out/ovda-local')
    policy=replace(resolve_live('video-quality',.5),stereo_layout='half-tb')
    report=dict(scope='controlled timeline/native readback; dense reference has no ground truth; not capture FPS',
                sources={},phases=[])
    try:
        for w,h,dropped,count in ((1280,720,False,24),(1280,720,True,96),
                                  (1056,608,True,96),(720,1280,True,96)):
            shape=select_profile(w,h,profiles)
            names=('dense','strict','retain')
            engines={};posts={}
            phase=dict(size=[w,h],canvas=shape,dropped=dropped,clips={})
            try:
                for name in names:
                    engines[name]=cls(directory=profiles[shape],profile=shape)
                    posts[name]=LiveSourceGpuTexture(w,h,policy,engines[name],diagnostic=True)
                for clip in ('FloorballGame','OfficeWalk','ParkingGarage'):
                    path=CORPUS/(clip+'.mp4')
                    digest=hashlib.sha256(path.read_bytes()).hexdigest()
                    if digest!=json.loads(path.with_suffix('.json').read_text())['sha256']:
                        raise ValueError('Public source identity changed')
                    report['sources'][clip]=digest
                    previous={name:None for name in names}
                    last={name:None for name in names}
                    data={name:dict(frames=0,resets=0,retained=0,cache_sum=0,full=0,
                                    raw_error=[],temporal_error=[],edge_error=[],sbs_mae=[]) for name in names}
                    cap=cv2.VideoCapture(str(path))
                    try:
                        scale=None
                        for index in range(count):
                            ok,bgr=cap.read()
                            if not ok:raise ValueError('Short public input')
                            rgb=np.ascontiguousarray(cv2.resize(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB),(w,h)))
                            sequence=index+1;stamp=1_000_000_000+round(index*1e9/60)
                            cut=index==count//2
                            selected=not dropped or index%4!=3
                            depths={};images={}
                            for name in names:
                                if name!='dense' and not selected:continue
                                engine,post,row=engines[name],posts[name],data[name]
                                prior=previous[name]
                                reason=reset_reason(prior[0] if prior else None,sequence,
                                    (w,h) if prior else None,(w,h),cut,
                                    previous_source_ns=prior[1] if prior else None,source_ns=stamp,
                                    ovda_short_skip=name=='retain')
                                if reason is not None:
                                    engine.reset({'start':'start','gap':'discontinuity','cut':'scene_cut'}[reason])
                                    post.reset();row['resets']+=1;last[name]=None
                                elif prior and sequence==prior[0]+2:row['retained']+=1
                                row['cache_sum']+=engine.used
                                row['full']+=int(engine.used==15)
                                with torch.cuda.stream(engine.stream):
                                    frame=GpuFrame(torch.from_numpy(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGRA)).to(engine.device),engine)
                                post.source_ns=stamp
                                token=post.infer(frame)
                                engine.stream.synchronize()
                                depths[name]=token.tensor.cpu().numpy().copy()[0]
                                # Cuts are controlled equally for all three timelines.
                                observation=replace(post.inspect_scene(frame),cut=False)
                                post.slot=index%2
                                slot=post.render(frame,token,scene=observation)
                                ow,oh=dimensions(w,h,policy.stereo_layout)
                                output=np.empty((oh,ow,4),np.uint8)
                                post.pool.check(post.pool.dll.live_pool_readback(post.pool.handle,slot,output.ctypes.data))
                                assert np.all(output[:,:,3]==255)
                                images[name]=output[:,:,:3].copy()
                                row['frames']+=1;previous[name]=(sequence,stamp)
                            if scale is None:
                                lo,hi=np.percentile(depths['dense'],[2,98]);scale=max(float(hi-lo),1e-6)
                            if not selected:continue
                            reference=depths['dense']
                            for name in ('strict','retain'):
                                value=depths[name];row=data[name]
                                row['raw_error'].append(float(np.abs(value-reference).mean())/scale*100)
                                edges=[float(np.abs(np.diff(value,axis=axis)-np.diff(reference,axis=axis)).mean())/scale*100
                                       for axis in (0,1)]
                                row['edge_error'].append(statistics.mean(edges))
                                row['sbs_mae'].append(float(np.abs(images[name].astype(np.int16)-images['dense'].astype(np.int16)).mean()))
                                # Evaluate the same selected source intervals for both
                                # candidates, including intervals where strict resets.
                                prior=last['dense-'+name] if 'dense-'+name in last else None
                                if prior is not None and not cut:
                                    old_value,old_reference=prior
                                    row['temporal_error'].append(float(np.abs((value-old_value)-(reference-old_reference)).mean())/scale*100)
                                last['dense-'+name]=(value.copy(),reference.copy())
                                if not dropped:
                                    np.testing.assert_array_equal(value,reference)
                                    np.testing.assert_array_equal(images[name],images['dense'])
                            if index==count-2 and dropped:
                                strip=np.concatenate([images[name] for name in names],axis=1)
                                preview=cv2.resize(strip,(1440,round(strip.shape[0]*1440/strip.shape[1])))
                                cv2.imwrite(str(args.output/f'{w}x{h}-{clip}.png'),cv2.cvtColor(preview,cv2.COLOR_BGR2RGB))
                    finally:cap.release()
                    result={}
                    for name,row in data.items():
                        result[name]={k:(dict(mean=statistics.mean(v),max=max(v)) if v else None) if isinstance(v,list) else v
                                      for k,v in row.items()}
                        result[name]['cached_past_mean']=row['cache_sum']/max(1,row['frames'])
                        result[name]['full_context_fraction']=row['full']/max(1,row['frames'])
                    phase['clips'][clip]=result
                    print(json.dumps(dict(size=[w,h],dropped=dropped,clip=clip,result=result)),flush=True)
                report['phases'].append(phase)
            finally:
                for post in posts.values():post.close()
                for engine in engines.values():engine.close()
                (args.output/'report.json').write_text(json.dumps(report,indent=2))
        report['passed']=True
    finally:(args.output/'report.json').write_text(json.dumps(report,indent=2))


if __name__=='__main__':main()
