"""Held-out known-disparity/temporal evaluation of current live model bindings."""
import argparse
from contextlib import ExitStack
from dataclasses import asdict
import csv
import hashlib
import itertools
import json
from pathlib import Path
import statistics
import subprocess
import time

import cv2
import h5py
import numpy as np
import torch

from evaluate_sbs_quality import open_session,Session,MODES
from screento3d_app.desktop_jobs import ROOT,BUNDLE
from screento3d_app.resources import configure_resource_root
from screento3d_app.spring_quality import fit_affine,align,spatial_error,temporal_geometry,temporal_error,error_metrics

TRACKS=('model_depth','app_disparity')
CONTRACT=dict(warmup=[1,32],calibration=[33,48],evaluation=[49,80],source_size=[1920,1080],
    source_hz=60,source_time_scope='fixed experimental 60Hz timestamps; not a claim about original movie frame rate',
    gt_sampling='official utility subsampling [::2,::2]; vector values remain 1080p pixels, no division by 2',
    calibration_method='per model/scene/track OLS scale+offset on fixed 8px grid in frames33-48; frozen for frames49-80',
    spatial='MAE/RMSE/bad1; finite nonnegative GT, including zero-disparity sky; no prediction-dependent masking',
    boundary='GT neighbor disparity jump >1px, dilated by 1px; same mask for every model',
    temporal='(pred_next at x+GTflow - pred_current) - (GTdisp2_FW - GTdisp1)',
    temporal_visibility='finite GT, in-frame 1px rim, abs(warp next GTdisp1 - current GTdisp2_FW)<=.5px, eroded1px',
    temporal_changing_depth='same visible mask with abs(GTdisp2_FW - GTdisp1)>=.1px',
    normalization='no framewise fitting, minmax, clipping or per-frame alignment in evaluator',
    model_scope='current causal GPU capture bindings; Small FP16, Base FP16, VDA mixed FP16, oVDA mixed FP16 c16',
    output_scope='strength.5 HalfTB VFGoff; sequential ordered inputs, no frame drops; not FPS or official stereo leaderboard')


def read_gt(root,scene,kind,index):
    extension='flo5' if kind.startswith('flow') else 'dsp5'
    path=root/'spring/train'/scene/kind/f'{kind}_{index:04d}.{extension}'
    with h5py.File(path,'r') as f:
        key='flow' if extension=='flo5' else 'disparity'
        if key not in f:raise ValueError(f'Invalid Spring HDF5 key: {path}')
        expected=(2160,3840,2) if extension=='flo5' else (2160,3840)
        if f[key].shape!=expected:raise ValueError('Unexpected Spring GT geometry')
        result=np.asarray(f[key][::2,::2],dtype=np.float32)
    return result


def aggregate(rows,key):
    measured=[r[key] for r in rows if r[key]['pixels']]
    n=sum(r['pixels'] for r in measured)
    return dict(pixels=n,mae_px=sum(r['mae_px']*r['pixels'] for r in measured)/n if n else None,
        rmse_px=(sum(r['rmse_px']**2*r['pixels'] for r in measured)/n)**.5 if n else None,
        bad1_percent=sum(r['bad1_percent']*r['pixels'] for r in measured)/n if n else None)


def run_scene(session,root,scene):
    samples={track:[] for track in TRACKS};targets=[];fits={};rows=[];resets=[]
    previous=None;previous_truth=None
    for index in range(1,81):
        path=root/'spring/train'/scene/'frame_left'/f'frame_left_{index:04d}.png'
        bgr=cv2.imread(str(path),cv2.IMREAD_COLOR)
        if bgr is None or bgr.shape!=(1080,1920,3):raise ValueError('Invalid Spring input')
        rgb=np.ascontiguousarray(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB))
        _,disparity,reason=session.frame(rgb,index-1)
        if reason:resets.append(dict(frame=index,reason=reason))
        predictions=dict(model_depth=session.raw_depth,app_disparity=disparity)
        if index<=32:continue
        truth=read_gt(root,scene,'disp1_left',index)
        if index<=48:
            target=truth[4::8,4::8];mask=np.isfinite(target)&(target>=0)
            targets.append(target[mask])
            for track in TRACKS:samples[track].append(predictions[track][4::8,4::8][mask])
            if index==48:
                fits={track:fit_affine(samples[track],targets) for track in TRACKS}
                samples.clear();targets.clear()
            continue
        if reason:raise ValueError(f'Reset during held-out scoring: {scene} frame {index}: {reason}')
        aligned={track:align(predictions[track],fits[track]) for track in TRACKS}
        row=dict(frame=index,spatial={track:spatial_error(aligned[track],truth) for track in TRACKS})
        if previous is not None:
            flow=read_gt(root,scene,'flow_FW_left',index-1)
            future=read_gt(root,scene,'disp2_FW_left',index-1)
            geometry=temporal_geometry(previous_truth,truth,future,flow)
            transported_truth=cv2.remap(truth,geometry[0],geometry[1],cv2.INTER_LINEAR)
            row['gt_sampling_control_from_previous']=error_metrics(transported_truth-future,geometry[2])
            row['temporal_from_previous']={track:temporal_error(previous[track],aligned[track],geometry) for track in TRACKS}
        rows.append(row);previous=aligned;previous_truth=truth
    if len(rows)!=32 or sum('temporal_from_previous' in r for r in rows)!=31:
        raise ValueError('Incomplete held-out Spring evaluation')
    summaries={}
    for track in TRACKS:
        spatial=[row['spatial'][track] for row in rows]
        temporal=[row['temporal_from_previous'][track] for row in rows if 'temporal_from_previous' in row]
        summary=dict(spatial=aggregate(spatial,'all'),spatial_edges=aggregate(spatial,'edges'),
            temporal=aggregate(temporal,'all'),temporal_edges=aggregate(temporal,'edges'),
            temporal_changing_depth=aggregate(temporal,'changing_depth'),
            temporal_frozen_control=aggregate(temporal,'frozen_control'),
            temporal_gt_sampling_control=aggregate([dict(control=row['gt_sampling_control_from_previous'])
                for row in rows if 'gt_sampling_control_from_previous' in row],'control'),
            temporal_valid_fraction=statistics.mean(row['valid_fraction'] for row in temporal))
        span=fits[track]['truth_span_px']
        summary['spatial_nmae_percent']=summary['spatial']['mae_px']/span*100 if span>=.1 else None
        summaries[track]=summary
    return dict(calibration=fits,resets=resets,summary=summaries,rows=rows)


def model_identity(model,owner,policy,backend,post):
    telemetry=owner.telemetry()
    artifacts={k:v for k,v in telemetry.items() if k in ('model_id','runtime','input_shape','plan_hashes','plan_sha256','model_sha256')}
    if model=='da2-small':
        from screento3d_app.trt_backend import _engine_path,_model_path,INPUT_SHAPE
        artifacts=dict(input_shape=list(INPUT_SHAPE),model_sha256=hashlib.sha256(_model_path().read_bytes()).hexdigest(),
            plan_sha256=hashlib.sha256(_engine_path().read_bytes()).hexdigest())
    return dict(policy=asdict(policy),runtime=backend.spec.runtime,artifacts=artifacts,
        renderer_sha256=hashlib.sha256(Path(post.dll._name).read_bytes()).hexdigest(),
        renderer_legacy_abi_sha256=post.library_sha256,engine_telemetry=telemetry)


def dashboard(output,report):
    def f(v):return 'N/A' if v is None else f'{v:.3f}'
    lines=['# Spring 정답 기반 품질 평가','',f"실행 상태: {'완료' if report['completed'] else '부분/실패'}",'',
        '낮을수록 좋습니다. 모든 시차·오차 단위는 원본 1920×1080 기준 px입니다.',
        '모델별·장면별 보정은 33–48프레임에서 한 번 구하고 고정합니다. 평가는 49–80프레임입니다.',
        '공식 스테레오 순위표가 아닌, 왼쪽 영상만 입력한 앱의 단안 모델·현재 후처리 비교입니다.','']
    csvrows=[];macro=[]
    for track in TRACKS:
        lines += [f"## {'모델 출력 자체' if track=='model_depth' else '앱의 최종 시차'}",'',
            '| 모델 | 장면 | 시차 MAE | 경계 MAE | 1px 초과 % | 시간축 RMSE | 깊이 변화 영역 RMSE | 시간 평가 영역 % |',
            '|---|---|---:|---:|---:|---:|---:|---:|']
        for row in report['cases']:
            s=row['result']['summary'][track]
            entry=dict(model=row['model'],scene=row['scene'],track=track,spatial_mae_px=s['spatial']['mae_px'],
                boundary_mae_px=s['spatial_edges']['mae_px'],bad1_percent=s['spatial']['bad1_percent'],
                nmae_percent=s['spatial_nmae_percent'],temporal_rmse_px=s['temporal']['rmse_px'],
                changing_depth_rmse_px=s['temporal_changing_depth']['rmse_px'],
                frozen_control_rmse_px=s['temporal_frozen_control']['rmse_px'],
                gt_sampling_control_rmse_px=s['temporal_gt_sampling_control']['rmse_px'],
                temporal_valid_percent=s['temporal_valid_fraction']*100)
            csvrows.append(entry)
            lines.append('| '+' | '.join([entry['model'],entry['scene']]+[f(entry[k]) for k in
                ('spatial_mae_px','boundary_mae_px','bad1_percent','temporal_rmse_px','changing_depth_rmse_px','temporal_valid_percent')])+' |')
        lines+=['','| 모델 | 완료 장면 수 | 장면 평균 MAE | 경계 MAE | 시간축 RMSE |','|---|---:|---:|---:|---:|']
        for model in report['models']:
            entries=[r for r in csvrows if r['model']==model and r['track']==track]
            if not entries:continue
            m=dict(model=model,track=track,scenes=len(entries))
            for key in ('spatial_mae_px','boundary_mae_px','temporal_rmse_px','nmae_percent'):
                values=[r[key] for r in entries if r[key] is not None]
                m[key]=statistics.mean(values) if values else None
            macro.append(m)
            lines.append('| '+' | '.join([model,str(len(entries))]+[f(m[k]) for k in ('spatial_mae_px','boundary_mae_px','temporal_rmse_px')])+' |')
    report['macro']=macro
    paired=[]
    for track in TRACKS:
        for a,b in itertools.combinations(report['models'],2):
            left={r['scene']:r for r in csvrows if r['model']==a and r['track']==track}
            right={r['scene']:r for r in csvrows if r['model']==b and r['track']==track}
            scenes=sorted(left.keys()&right.keys())
            for metric in ('spatial_mae_px','boundary_mae_px','temporal_rmse_px'):
                differences=[left[s][metric]-right[s][metric] for s in scenes
                    if left[s][metric] is not None and right[s][metric] is not None]
                if not differences:continue
                delta=np.asarray(differences)
                draws=np.random.default_rng(19).choice(delta,(10000,len(delta)),replace=True).mean(axis=1)
                paired.append(dict(track=track,a=a,b=b,metric=metric,scenes=len(delta),a_wins=int((delta<0).sum()),
                    b_wins=int((delta>0).sum()),mean_a_minus_b=float(delta.mean()),
                    exploratory_scene_bootstrap_95=np.quantile(draws,[.025,.975]).tolist()))
    report['paired']=paired
    lines+=['','정답의 실제 깊이 변화를 뺀 시간축 오차입니다. 흐름과 가시성 판정은 모델 예측과 독립적입니다.',
        '시차를 고정해 일렁임만 없앤 출력도 정답 변화와 다르면 벌점을 받습니다. 정지 시차 대조값은 CSV에 포함합니다.',
        '모델 출력은 후처리 전 상대 역깊이이며, 앱 시차는 범위·시간·경계·돌출 보정 뒤의 출력입니다. 각각 따로 고정 보정합니다.',
        '모든 장면에 같은 프레임·60Hz 실험 시각·입체감0.5·Half TB·VFG OFF를 적용했습니다. 원본 영화 FPS나 실시간 FPS 측정이 아닙니다.',
        '네 개 합성 장면의 제한된 평가입니다. 장면별 승패와 탐색적 신뢰구간을 JSON에 남기며, 전체 영상·시청 편안함의 우열로 일반화하지 않습니다.','']
    (output/'summary.md').write_text('\n'.join(lines),encoding='utf-8')
    if csvrows:
        with (output/'cases.csv').open('w',newline='',encoding='utf-8') as handle:
            writer=csv.DictWriter(handle,fieldnames=list(csvrows[0]));writer.writeheader();writer.writerows(csvrows)
    with (output/'frames.csv').open('w',newline='',encoding='utf-8') as handle:
        writer=csv.writer(handle);writer.writerow(('model','scene','frame','track','spatial_mae_px','temporal_rmse_px'))
        for case in report['cases']:
            for row in case['result']['rows']:
                for track in TRACKS:
                    temporal=row.get('temporal_from_previous',{}).get(track,{})
                    writer.writerow((case['model'],case['scene'],row['frame'],track,row['spatial'][track]['all']['mae_px'],temporal.get('all',{}).get('rmse_px')))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=ROOT/'out/spring-source')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--model',action='append',choices=tuple(MODES))
    parser.add_argument('--noncommercial',action='store_true')
    args=parser.parse_args();models=args.model or list(MODES)
    if 'ovda-small-c16' in models and not args.noncommercial:raise ValueError('Confirm existing noncommercial oVDA scope')
    manifest=json.loads((args.source/'manifest.json').read_text())
    if not manifest['completed']:raise ValueError('Spring subset incomplete')
    args.output.mkdir(parents=True,exist_ok=False)
    report=dict(completed=False,contract=CONTRACT,source_manifest_sha256=hashlib.sha256((args.source/'manifest.json').read_bytes()).hexdigest(),
        dataset=manifest['plan']['dataset'],sequences=manifest['plan']['sequences'],attribution=manifest['attribution'],
        git_head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        git_dirty=bool(subprocess.check_output(['git','status','--porcelain'],text=True).strip()),
        gpu=torch.cuda.get_device_name(),torch=torch.__version__,h5py=h5py.__version__,models={},cases=[])
    (args.output/'protocol.json').write_text(json.dumps(CONTRACT,indent=2))
    configure_resource_root(BUNDLE);cv2.setNumThreads(1)
    try:
        for entry in manifest['entries']:
            if hashlib.sha256((args.source/entry['path']).read_bytes()).hexdigest()!=entry['sha256']:
                raise ValueError('Spring member checksum mismatch')
        print('All Spring subset hashes verified',flush=True)
        for model in models:
            with ExitStack() as stack:
                backend,owner,post,policy=open_session(stack,model,1920,1080,'half-tb',args.noncommercial)
                report['models'][model]=model_identity(model,owner,policy,backend,post)
                for scene in report['sequences']:
                    started=time.monotonic()
                    session=Session(backend,owner,post,policy,model,collect_raw=True)
                    result=run_scene(session,args.source,scene)
                    report['cases'].append(dict(model=model,scene=scene,result=result))
                    dashboard(args.output,report)
                    (args.output/'report.json').write_text(json.dumps(report,indent=2))
                    print(json.dumps(dict(model=model,scene=scene,seconds=time.monotonic()-started,summary=result['summary'])),flush=True)
                report['models'][model]=model_identity(model,owner,policy,backend,post)
        report['completed']=True
    except BaseException as error:
        report['error']=repr(error);raise
    finally:
        dashboard(args.output,report)
        (args.output/'report.json').write_text(json.dumps(report,indent=2))


if __name__=='__main__':main()
