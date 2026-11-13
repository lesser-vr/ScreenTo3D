"""Matched native SBS quality dashboard; no universal score or live-FPS claim."""
import argparse
from contextlib import ExitStack
from dataclasses import asdict,replace
import csv
import ctypes as ct
import hashlib
import json
from pathlib import Path
import statistics
import subprocess

import cv2
import numpy as np
import torch

from screento3d_app.desktop_jobs import ROOT,BUNDLE
from screento3d_app.resources import configure_resource_root
from screento3d_app.live_model import model_adapter
from screento3d_app.live_policy import resolve_live
from screento3d_app.live_sbs import resolve_history_policy,reset_reason
from screento3d_app.live_backend import binding
from screento3d_app.optional_models import installed_path,available
from screento3d_app.live_source_gpu_texture import LiveSourceGpuTexture
from screento3d_app.gpu_frame import GpuFrame
from screento3d_app.sbs_quality import motion_map,temporal_disparity,edge_reprojection,step_response,unpack_half_tb
from public_test_media import CORPUS,SOURCES,ATTRIBUTION

MODES={'da2-small':'performance','da2-base':'balanced','vda-small':'video-quality','ovda-small-c16':'video-quality'}
FLOW_SIZE=(480,270)


def open_session(stack,model,width,height,layout,noncommercial):
    from screento3d_app.trt_backend import DepthEngine
    engine_path=''
    if model!='da2-small':
        if model=='ovda-small-c16':engine_path=str(ROOT/'out/ovda-local')
        else:
            path=installed_path(model)
            engine_path=str(path if available(model,path) else ROOT/'out'/('da2-base-local' if model=='da2-base' else 'vda-local'))
    selected=dict(model=model,engine=engine_path,runtime=str(BUNDLE/'runtime'),noncommercial=noncommercial)
    backend=binding(selected,MODES[model],dict(width=width,height=height),DepthEngine,lambda value:value)
    adapter=model_adapter(model)
    backend=adapter.bind_capture(backend,True)
    owner=stack.enter_context(backend.engine_factory(None))
    policy=adapter.apply_live_policy(replace(resolve_live(MODES[model],.5),depth_backend=model,stereo_layout=layout))
    post=stack.enter_context(adapter.renderer_factory(native=True,gpu_capture=True)(width,height,policy,owner,diagnostic=True))
    if adapter.coalesced_history:post.configure_live_quality('detail')
    post.dll.live_shift_snapshot.argtypes=[ct.c_void_p,ct.c_void_p]
    return backend,owner,post,policy


class Session:
    def __init__(self,backend,owner,post,policy,model,*,hz=60,collect_raw=False):
        self.backend,self.owner,self.post,self.policy,self.model=backend,owner,post,policy,model
        self.previous_sequence=self.previous_stamp=None
        self.history=resolve_history_policy(model)
        self.hz,self.collect_raw=hz,collect_raw
        self.raw_depth=None
    def frame(self,rgb,index,*,cut=False):
        owner,post=self.owner,self.post;h,w=rgb.shape[:2]
        if getattr(owner,'native',False):
            bgra=owner.memory.from_numpy(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGRA));frame=GpuFrame(bgra,owner)
        else:
            stream=getattr(owner,'torch_stream',owner.stream)
            with torch.cuda.stream(stream):
                frame=GpuFrame(torch.from_numpy(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGRA)).to(owner.device),owner)
        scene=post.inspect_scene(frame)
        stamp=1_000_000_000+round(index*1e9/self.hz)
        reason=reset_reason(self.previous_sequence,index,(w,h),(w,h),cut or scene.cut,
            previous_source_ns=self.previous_stamp,source_ns=stamp,**self.history)
        if reason:
            self.backend.reset(owner,{'start':'start','cut':'scene_cut','gap':'discontinuity'}[reason])
            post.reset();scene=None
        token=post.infer(frame);post.source_ns=stamp;post.slot=index%2
        if self.collect_raw:
            from screento3d_app.trt_backend import _cuda,cudart
            raw=np.empty((h,w),np.float32)
            if self.model=='da2-small':
                post.dll.live_resize_probe.argtypes=[ct.c_void_p,ct.c_void_p,ct.c_void_p]
                post._check(post.dll.live_resize_probe(post.handle,token.pointer,raw.ctypes.data))
            else:
                _cuda(cudart.cudaMemcpyAsync(raw.ctypes.data,token.pointer,raw.nbytes,
                    cudart.cudaMemcpyKind.cudaMemcpyDeviceToHost,token.stream))
                _cuda(cudart.cudaStreamSynchronize(token.stream))
            if not np.isfinite(raw).all():raise ValueError('Nonfinite raw model depth')
            self.raw_depth=raw
        slot=post.render(frame,token,scene=scene)
        pixels=np.empty((post.pool.height,post.pool.width,4),np.uint8)
        post.pool.check(post.pool.dll.live_pool_readback(post.pool.handle,slot,pixels.ctypes.data))
        shift=np.empty((h,w),np.float32)
        post._check(post.dll.live_shift_snapshot(post.handle,shift.ctypes.data))
        self.previous_sequence=index;self.previous_stamp=stamp
        return pixels,shift*2,reason


def natural_case(session,path,count,width,height):
    rows=[];previous_rgb=previous_disparity=None;last_reset=0
    cap=cv2.VideoCapture(str(path))
    try:
        for index in range(count):
            ok,bgr=cap.read()
            if not ok:raise ValueError('Short natural quality fixture')
            rgb=np.ascontiguousarray(cv2.cvtColor(cv2.resize(bgr,(width,height)),cv2.COLOR_BGR2RGB))
            pixels,disparity,reason=session.frame(rgb,index)
            small_rgb=cv2.resize(rgb,FLOW_SIZE,interpolation=cv2.INTER_AREA)
            # Values retain logical restored-eye 4K pixels; only locations shrink.
            small_disparity=cv2.resize(disparity,FLOW_SIZE,interpolation=cv2.INTER_AREA)*(3840/width)
            eyes=unpack_half_tb(pixels,*FLOW_SIZE)
            edge=edge_reprojection(small_rgb,eyes,small_disparity*(FLOW_SIZE[0]/3840))
            if reason is not None:last_reset=index
            row=dict(frame=index,source_time_ms=index*1000/60,reset=reason,warmup=index-last_reset<32,
                     signed_d05_px=float(np.quantile(small_disparity,.05)),
                     signed_d95_px=float(np.quantile(small_disparity,.95)),
                     abs_d95_px=float(np.quantile(np.abs(small_disparity),.95)),edge=edge,temporal=None)
            if previous_rgb is not None and reason is None:
                row['temporal']=temporal_disparity(previous_disparity,small_disparity,motion_map(previous_rgb,small_rgb))
            rows.append(row);previous_rgb=small_rgb;previous_disparity=small_disparity
    finally:cap.release()
    pairs=[row['temporal'] for row in rows if row['temporal'] is not None and not row['warmup']]
    def temporal_summary(key):
        measured=[p[key] for p in pairs if p[key]['pixels'] and p[key]['rmse_px'] is not None]
        n=sum(item['pixels'] for item in measured)
        return dict(rmse_px=(sum(item['rmse_px']**2*item['pixels'] for item in measured)/n)**.5 if n else None,
                    max_pair_p95_px=max((item['p95_abs_px'] for item in measured),default=None),pixels=n)
    edges=[eye for row in rows if not row['warmup'] for eye in row['edge'] if eye['pixels']]
    n=sum(e['pixels'] for e in edges)
    usable=[row for row in rows if not row['warmup']]
    return dict(rows=rows,summary=dict(measured_pairs=len(pairs),warmup_frames=sum(row['warmup'] for row in rows),
        temporal=temporal_summary('all'),temporal_edges=temporal_summary('edges'),
        valid_fraction_mean=statistics.mean(p['valid_fraction'] for p in pairs) if pairs else None,
        edge_valid_fraction_mean=statistics.mean(p['edge_valid_fraction'] for p in pairs) if pairs else None,
        source_edge_rgb_mae=sum(e['mae']*e['pixels'] for e in edges)/n if n else None,
        source_edge_coverage_mean=statistics.mean(e['edge_coverage'] for e in edges) if edges else None,
        source_edge_pixels=n,abs_d95_px_mean=statistics.mean(row['abs_d95_px'] for row in usable) if usable else None,
        signed_disparity_span_px_mean=statistics.mean(row['signed_d95_px']-row['signed_d05_px'] for row in usable) if usable else None,
        reset_counts={reason:sum(row['reset']==reason for row in rows) for reason in ('start','gap','cut','resize')}))


def response_case(session,background,patch,width,height):
    """Within-model settling after a constant-size card relocates at t=0.

    Target is each model's stationary new-view output, not known physical depth.
    Input change covers <=12.5% of pixels, below the ordinary .18 cut threshold.
    """
    bg=cv2.resize(background,(width,height));ph,pw=height//4,width//4
    card=cv2.resize(patch,(pw,ph));y=height//3;old_x=width//8;new_x=width*5//8
    old=bg.copy();old[y:y+ph,old_x:old_x+pw]=card
    new=bg.copy();new[y:y+ph,new_x:new_x+pw]=card
    roi=(slice(y+ph//4,y+ph*3//4),slice(new_x+pw//4,new_x+pw*3//4))
    before=[];after=[];resets=[]
    for index in range(192):
        _,d,reason=session.frame(old if index<96 else new,index)
        if reason:resets.append(dict(frame=index,reason=reason))
        value=float(np.median(d[roi]))*(3840/width)
        (before if index<96 else after).append(value)
    initial=float(np.mean(before[-8:]));target=float(np.mean(after[-8:]))
    result=step_response(after,initial,target)
    result.pop('gain',None)  # The target here is a measured plateau, not known truth.
    tail_span=float(np.ptp(after[-8:]));amplitude=target-initial
    if any(item['frame']>=96 for item in resets):
        result.update(t90_ms=None,first_90_ms=None,updates_to_90=None,reason='reset_during_step')
    elif tail_span>max(.02,abs(amplitude)*.02):
        result.update(t90_ms=None,first_90_ms=None,updates_to_90=None,reason='target_not_settled')
    return dict(**result,initial_px=initial,target_px=target,amplitude_px=amplitude,tail_span_px=tail_span,
                before_px=before,after_px=after,resets=resets,
                scope='within-model settling of relocated composite card; source-time 60Hz; not wall/display latency or depth truth')


def synthetic_boundary():
    """Reuse the independent layered rendering oracle, with current compiled code."""
    from check_stereo_detail import setup,synthetic
    from screento3d_app.live_gpu_candidate import DLL_PATH,DLL_SHA256
    from screento3d_app.portable_cuda import binary
    path,pin=binary(DLL_PATH,DLL_SHA256)
    dll=setup(path,pin);result=synthetic(dll)
    from check_stereo_geometry_gpu import context
    from screento3d_app.live_texture_pool import LiveTexturePool
    from screento3d_app.stereo_layout import pack
    rgb=np.random.default_rng(31).integers(0,256,(32,128,3),np.uint8)
    depth=np.full((32,128),.5,np.float32);stream=torch.cuda.Stream()
    with ExitStack() as stack:
        handle=context(stack,dll,rgb,depth,stream)
        pool=stack.enter_context(LiveTexturePool(128,32,diagnostic=True,layout='half-tb'))
        pixels=np.empty((32,128,4),np.uint8)
        pool.check(pool.dll.live_pool_publish(pool.handle,handle,.5,12,1,depth.ctypes.data,0,0))
        pool.check(pool.dll.live_pool_readback(pool.handle,0,pixels.ctypes.data))
        expected=pack(np.concatenate((rgb,rgb),axis=1),'half-tb')
        np.testing.assert_array_equal(pixels[:,:,:3],expected)
        assert np.all(pixels[:,:,3]==255)
    return dict(scope='known layered RGB/depth, 1920px eyes; renderer component, excludes model inference',
                detail_fill_vs_disabled=result,native_half_tb_zero_disparity_exact=True,dll_sha256=pin)


def write_dashboard(output,report):
    def value(number):return 'N/A' if number is None else f'{number:.3f}'
    def percent(number):return value(number*100 if number is not None else None)
    lines=['# SBS 품질 측정 결과','',
        '실행 상태: '+('완료' if report['completed'] else '실패 또는 부분 결과'),'',
        '실제 영상 수치는 시간·영상 보존의 대리 지표입니다. 합성 경계 검사는 별도로 알려진 정답과 비교합니다.',
        '추종 반응은 모델별 입력 변화에 대한 반응이며 캡처·연산·디스플레이 지연이 아닙니다. 종합 품질 점수는 계산하지 않습니다.',
        '입력은 1920×1080, 60Hz 시각 기준 재생이며 시차 값만 가로 3840 기준 픽셀로 환산합니다.', '',
        '| 모델 | 영상 | 시차 변화 RMS, 4K px | 경계 시차 RMS, 4K px | 시간 평가 영역 % | 경계 평가 영역 % | 절대 시차 P95, 4K px |',
        '|---|---|---:|---:|---:|---:|---:|']
    csvrows=[]
    for row in report['natural']:
        s=row['result']['summary'];entry=dict(model=row['model'],clip=row['clip'],
            temporal_rms_4k_px=s['temporal']['rmse_px'],source_edge_rgb_mae=s['source_edge_rgb_mae'],
            temporal_edge_rms_4k_px=s['temporal_edges']['rmse_px'],temporal_edge_coverage=s['edge_valid_fraction_mean'],
            valid_fraction=s['valid_fraction_mean'],source_edge_coverage=s['source_edge_coverage_mean'],abs_d95_4k_px=s['abs_d95_px_mean'],
            signed_span_4k_px=s['signed_disparity_span_px_mean'])
        span=entry['signed_span_4k_px']
        entry['temporal_rms_over_span']=entry['temporal_rms_4k_px']/span if span is not None and span>=.1 and entry['temporal_rms_4k_px'] is not None else None
        csvrows.append(entry)
        lines.append('| '+ ' | '.join([row['model'],row['clip'],value(entry['temporal_rms_4k_px']),value(entry['temporal_edge_rms_4k_px']),
            value(entry['valid_fraction']*100 if entry['valid_fraction'] is not None else None),
            value(entry['temporal_edge_coverage']*100 if entry['temporal_edge_coverage'] is not None else None),value(entry['abs_d95_4k_px'])])+' |')
    lines+=['','| 모델 | 영상 | 경계 RGB 재투영 차이, 0–255 | 가시 경계 평가 영역 % |','|---|---|---:|---:|']
    for entry in csvrows:
        lines.append(f"| {entry['model']} | {entry['clip']} | {value(entry['source_edge_rgb_mae'])} | {percent(entry['source_edge_coverage'])} |")
    lines+=['','| 모델 | 최초 90% 도달, ms | ±10% 안에서 안정화, ms | 반응 변화폭, 4K px | 측정 상태 |','|---|---:|---:|---:|---|']
    for row in report['response']:
        result=row['result'];lines.append(f"| {row['model']} | {value(result.get('first_90_ms'))} | {value(result['t90_ms'])} | {value(result['amplitude_px'])} | {result['reason'] or 'measured'} |")
    if report.get('synthetic'):
        lines+=['','Known layered renderer oracle (model inference excluded):','',
                '| Foreground width, px | Strength | Boundary RGB MAE: fill off | Fill on |',
                '|---|---:|---:|---:|']
        for row in report['synthetic']['detail_fill_vs_disabled']['layered']:
            lines.append(f"| {row['thickness']} | {row['strength']} | {value(row['rgb_mae'][0])} | {value(row['rgb_mae'][1])} |")
    lines+=['','시차가 작거나 깊이가 평평해도 변화량은 작아집니다. 시차 크기·평가 영역·반응 변화폭을 함께 보세요.',
            '모든 모델에 같은 입력 프레임·시각, 입체감 0.5, Half TB, VFG OFF를 사용했습니다. 초기화 이후 32프레임은 실제 영상 집계에서 제외합니다. 모델 입력 크기와 후처리는 앱의 현재 기본 정책을 유지합니다.',
            '실제 영상의 RGB·움직임 분석은 480×270에서 수행합니다. 가려지거나 대응이 불확실한 영역은 제외합니다. 이 수치에는 실제 숨겨진 배경이나 깊이의 정답이 없으며, 실제 물체의 깊이 변화도 시간 변화량에 포함됩니다.',
            '최초 90% 도달 이후 과도 응답이 남을 수 있어 안정화 시간을 함께 기록합니다. 목표 변화가 너무 작거나 관찰 구간에서 안정되지 않으면 N/A입니다.',
            '이 결과는 깊이 정답 정확도, 실제 모니터의 편안함 또는 실시간 FPS를 판정하지 않습니다.','']
    (output/'summary.md').write_text('\n'.join(lines),encoding='utf-8')
    if csvrows:
        with (output/'natural.csv').open('w',newline='',encoding='utf-8') as handle:
            writer=csv.DictWriter(handle,fieldnames=list(csvrows[0]));writer.writeheader();writer.writerows(csvrows)
    with (output/'response.csv').open('w',newline='',encoding='utf-8') as handle:
        writer=csv.writer(handle);writer.writerow(('model','source_time_ms','disparity_4k_px'))
        for row in report['response']:
            values=row['result']['before_px']+row['result']['after_px']
            writer.writerows((row['model'],(i-96)*1000/60,value) for i,value in enumerate(values))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--model',action='append',choices=tuple(MODES))
    parser.add_argument('--frames',type=int,default=120,choices=range(32,361))
    parser.add_argument('--noncommercial',action='store_true')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    models=args.model or list(MODES)
    if 'ovda-small-c16' in models and not args.noncommercial:raise ValueError('Confirm existing oVDA noncommercial use with --noncommercial')
    configure_resource_root(BUNDLE);cv2.setNumThreads(1)
    report=dict(completed=False,scope=__doc__,gpu=torch.cuda.get_device_name(),torch=torch.__version__,
        git_head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        git_dirty=bool(subprocess.check_output(['git','status','--porcelain'],text=True).strip()),
        attribution=ATTRIBUTION,source_size=[1920,1080],flow_size=list(FLOW_SIZE),hz=60,strength=.5,layout='half-tb',vfg=False,
        synthetic=None,natural=[],response=[],sources={},models={})
    try:
        report['synthetic']=synthetic_boundary()
        for clip in SOURCES:
            path=CORPUS/(clip+'.mp4');record=json.loads(path.with_suffix('.json').read_text())
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            if digest!=record['sha256'] or record['source_sha256']!=SOURCES[clip]:raise ValueError('Public fixture identity mismatch')
            report['sources'][clip]=record
        capture=cv2.VideoCapture(str(CORPUS/'OfficeWalk.mp4'));ok,bg=capture.read();capture.release();assert ok
        capture=cv2.VideoCapture(str(CORPUS/'FloorballGame.mp4'));ok,card=capture.read();capture.release();assert ok
        bg=cv2.cvtColor(bg,cv2.COLOR_BGR2RGB);card=cv2.cvtColor(card,cv2.COLOR_BGR2RGB)[200:700,500:1100]
        for model in models:
            with ExitStack() as stack:
                backend,owner,post,policy=open_session(stack,model,1920,1080,'half-tb',args.noncommercial)
                for clip in SOURCES:
                    session=Session(backend,owner,post,policy,model)
                    result=natural_case(session,CORPUS/(clip+'.mp4'),args.frames,1920,1080)
                    row=dict(model=model,clip=clip,result=result);report['natural'].append(row)
                    print(json.dumps(dict(model=model,clip=clip,summary=result['summary'])),flush=True)
                    (args.output/'report.json').write_text(json.dumps(report,indent=2))
                session=Session(backend,owner,post,policy,model)
                response=response_case(session,bg,card,1920,1080)
                report['response'].append(dict(model=model,result=response))
                telemetry=owner.telemetry()
                report['models'][model]=dict(policy=asdict(policy),runtime=backend.spec.runtime,
                    artifacts={k:v for k,v in telemetry.items() if k in ('model_id','runtime','input_shape','plan_hashes','plan_sha256','model_sha256')})
                if model=='da2-small':
                    from screento3d_app.trt_backend import _engine_path,_model_path,INPUT_SHAPE
                    report['models'][model]['artifacts']=dict(model_id=model,input_shape=list(INPUT_SHAPE),
                        model_sha256=hashlib.sha256(_model_path().read_bytes()).hexdigest(),
                        plan_sha256=hashlib.sha256(_engine_path().read_bytes()).hexdigest())
                print(json.dumps(dict(model=model,response=response)),flush=True)
        report['completed']=True
    except BaseException as error:
        report['error']=repr(error);raise
    finally:
        (args.output/'report.json').write_text(json.dumps(report,indent=2));write_dashboard(args.output,report)


if __name__=='__main__':main()
