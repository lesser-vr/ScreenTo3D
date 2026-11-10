"""Calibrated native SBS RGB versus independent central/left/right 3D renders."""
import argparse
from contextlib import ExitStack
from dataclasses import replace
import csv
import ctypes as ct
import hashlib
import itertools
import json
import os
from pathlib import Path
import statistics
import subprocess
import time

import cv2
import numpy as np
import torch

from evaluate_sbs_quality import open_session,Session,MODES
from evaluate_spring_quality import model_identity
from depthsbs_app.desktop_jobs import ROOT,BUNDLE
from depthsbs_app.resources import configure_resource_root
from depthsbs_app.spring_quality import fit_affine
from depthsbs_app.sbs_rgb_quality import rgb_metrics,restored_eyes,reference_eyes
from depthsbs_app.live_texture_pool import LiveTexturePool
from sbs_rgb_fixture import WIDTH,HEIGHT,BASELINE,CONVERGENCE_Z,SCENES

LAYOUTS=('full-sbs','half-tb')
REGIONS=('all','edges','disoccluded','visible_interior')
METRIC_PINS=dict(backbone_sha256='7be5be791159472b1fbf3c69796f7cb30dca7ad8466c2df70058c37116cdee02',
    linear_sha256='df73285e35b22355a2df87cdb6b70b343713b667eddbda73e1977e0c860835c0')
CONTRACT=dict(source='project-authored four analytic three-view scenes, 1280x720; no Spring RGB claim',
    camera=dict(focal=.9*WIDTH,baseline_m=BASELINE,convergence_z_m=CONVERGENCE_Z),
    warmup_updates=32,calibration_updates=16,evaluation_frames=16,
    calibration='fixed OLS on postprocessed projection depth vs GT inverse Z; frame0 only, updates33-48; no scoring-frame fit',
    projection='same physical cameras after fixed model/scene scale+convergence calibration; RGB, postprocessing and native output retained',
    benchmark_only_changes='disable nonlinear disparity budget and stereo-window masks for physical reference matching; no app preference change',
    formats=list(LAYOUTS),sampling='GT HalfTB independently integer-box reduced then bilinearly restored, same logical eye grid as native',
    metrics='per-eye cropped PSNR, Gaussian RGB SSIM, LPIPS-Alex v0.1; GT-boundary/disocclusion RGB MAE',
    masks='GT-only; outer8rows/16columns excluded identically; hidden background still scored',
    aggregation='mean per eye/frame then equal scene weight; no combined quality score',
    controls='native known-depth oracle, duplicate central zero stereo and swapped GT eyes; identity and camera-unit tests',
    scope='calibrated render quality on procedural scenes; not unchanged-default geometry, real footage, FPS or comfort acceptance')


def load_frame(root,scene,index):
    folder=root/scene
    def rgb(name):
        bgr=cv2.imread(str(folder/f'{index:02d}-{name}.png'))
        if bgr is None or bgr.shape!=(HEIGHT,WIDTH,3):raise ValueError('Invalid three-view fixture')
        return np.ascontiguousarray(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB))
    with np.load(folder/f'{index:02d}-truth.npz',allow_pickle=False) as f:truth={k:f[k] for k in f.files}
    return rgb('center'),[rgb('left'),rgb('right')],truth


class Metrics:
    def __init__(self):
        os.environ['TORCH_HOME']=str(ROOT/'out/sbs-metric-weights')
        import lpips
        backbone=Path(os.environ['TORCH_HOME'])/'hub/checkpoints/alexnet-owt-7be5be79.pth'
        if not backbone.is_file():raise FileNotFoundError('Prepare official LPIPS AlexNet weights before measurement')
        linear=Path(lpips.__file__).parent/'weights/v0.1/alex.pth'
        for path,key in ((backbone,'backbone_sha256'),(linear,'linear_sha256')):
            if hashlib.sha256(path.read_bytes()).hexdigest()!=METRIC_PINS[key]:raise ValueError('LPIPS trusted metric weight mismatch')
        self.network=lpips.LPIPS(net='alex',version='0.1',verbose=False).eval().cuda()
        self.identity=dict(package='lpips==0.1.4',network='AlexNet',version='0.1',precision='FP32',
            backbone_sha256=hashlib.sha256(backbone.read_bytes()).hexdigest(),
            linear_sha256=hashlib.sha256(linear.read_bytes()).hexdigest())
    def score(self,actual,expected,truth,*,sides=('left','right')):
        # Batch eyes together, excluding only the same GT-declared outer rim.
        def tensor(eyes):return torch.from_numpy(np.stack([a[8:-8,16:-16].transpose(2,0,1) for a in eyes])).to('cuda',torch.float32)/127.5-1
        with torch.inference_mode():distances=self.network(tensor(actual),tensor(expected)).flatten().cpu().tolist()
        output=[]
        for i,side in enumerate(sides):
            result=rgb_metrics(actual[i],expected[i],truth[side+'_all'])
            result['lpips']=float(distances[i]);result['regions']={}
            difference=actual[i].astype(np.float32)-expected[i].astype(np.float32)
            for region in REGIONS[1:]:
                mask=truth[side+'_'+region];values=difference[mask]
                result['regions'][region]=dict(pixels=int(mask.sum()),mae=float(np.abs(values).mean()) if values.size else None,
                    mse=float(np.mean(values.astype(np.float64)**2)) if values.size else None)
            output.append(result)
        return output


def summarize(rows):
    eyes=[eye for row in rows for eye in row['eyes']]
    result={}
    for key in ('mae','psnr_db','ssim','lpips'):
        values=[e[key] for e in eyes if e[key] is not None]
        result[key]=statistics.mean(values) if values else None
    result['perfect_images']=sum(bool(e.get('perfect')) for e in eyes)
    result['regions']={}
    for region in REGIONS[1:]:
        values=[e['regions'][region] for e in eyes if e['regions'][region]['pixels']]
        n=sum(e['pixels'] for e in values)
        result['regions'][region]=dict(pixels=n,mae=sum(e['mae']*e['pixels'] for e in values)/n if n else None)
    return result


def read_pool(pool,handle,convergence,scale,index,refined=None):
    pool.check(pool.dll.live_pool_publish(pool.handle,handle,convergence,scale,1,
        refined.ctypes.data if refined is not None else None,index,0))
    pixels=np.empty((pool.height,pool.width,4),np.uint8)
    pool.check(pool.dll.live_pool_readback(pool.handle,index,pixels.ctypes.data))
    return pixels


def configure_camera_comparison(post):
    post.dll.live_set_disparity_budget.argtypes=[ct.c_void_p,ct.c_int]
    post._check(post.dll.live_set_disparity_budget(post.handle,0))
    post.dll.live_set_window.argtypes=[ct.c_void_p,ct.c_double,ct.c_int]
    post._check(post.dll.live_set_window(post.handle,-1,1))
    post.window_clock=None;post.screen_plane=None
    post.dll.live_detail_snapshot.argtypes=[ct.c_void_p,ct.c_void_p]


def run_model_scene(model,scene,root,metrics,stack,backend,owner,post,policy,half,output):
    configure_camera_comparison(post)
    # Restore the ordinary preset before the new scene's one-time calibration.
    post.policy=policy;post.stereo_convergence=policy.convergence
    session=Session(backend,owner,post,policy,model)
    center,_,initial=load_frame(root,scene,0)
    samples=[];targets=[];resets=[]
    for index in range(48):
        _,_,reason=session.frame(center,index)
        if reason:resets.append(dict(frame=index,reason=reason))
        if index>=32:
            depth=np.empty((HEIGHT,WIDTH),np.float32)
            post._check(post.dll.live_detail_snapshot(post.handle,depth.ctypes.data))
            samples.append(depth[4::8,4::8].ravel());targets.append(initial['inverse_depth'][4::8,4::8].ravel())
    fit=fit_affine(samples,targets)
    fit['truth_inverse_depth_span_m_inv']=fit.pop('truth_span_px')
    fit['truth_inverse_depth_mean_m_inv']=fit.pop('truth_mean_px')
    scale=.9*WIDTH*BASELINE*fit['scale'];convergence=(1/CONVERGENCE_Z-fit['offset'])/fit['scale']
    if scale<1 or scale>WIDTH*.2 or not np.isfinite(convergence):raise ValueError('Invalid calibrated camera projection')
    post.policy=replace(policy,divergence=scale/WIDTH);post.stereo_convergence=convergence
    rows={layout:[] for layout in LAYOUTS}
    for frame in range(1,17):
        center,truth_eyes,truth=load_frame(root,scene,frame)
        full,_,reason=session.frame(center,47+frame)
        if reason:raise ValueError('Unexpected reset during scored RGB frames')
        packed=dict(zip(LAYOUTS,(full,read_pool(half,post.handle,convergence,scale,frame%2))))
        for layout,pixels in packed.items():
            actual=restored_eyes(pixels,layout,WIDTH,HEIGHT);expected=reference_eyes(truth_eyes,layout)
            rows[layout].append(dict(frame=frame,eyes=metrics.score(actual,expected,truth)))
            if frame==8:
                path=output/f'{scene}-{model}-{layout}.png'
                cv2.imwrite(str(path),cv2.cvtColor(np.concatenate(actual,axis=1),cv2.COLOR_RGB2BGR))
    return dict(calibration=dict(**fit,projection_scale=scale,convergence=convergence),resets=resets,
                layouts={layout:dict(summary=summarize(values),rows=values) for layout,values in rows.items()})


def oracle_scene(root,scene,metrics,output):
    from check_stereo_geometry_gpu import load,context,check_cuda
    from depthsbs_app.live_gpu_candidate import DLL_PATH,DLL_SHA256
    from depthsbs_app.portable_cuda import binary
    path,pin=binary(DLL_PATH,DLL_SHA256);dll=load(path,pin)
    dll.live_set_detail.argtypes=[ct.c_void_p,ct.c_int]
    dll.live_set_subpixel.argtypes=[ct.c_void_p,ct.c_int]
    dll.live_set_coverage.argtypes=[ct.c_void_p,ct.c_int]
    dll.live_set_disparity_budget.argtypes=[ct.c_void_p,ct.c_int]
    dll.live_set_window.argtypes=[ct.c_void_p,ct.c_double,ct.c_int]
    rows={layout:[] for layout in LAYOUTS};controls=[]
    with ExitStack() as stack:
        stream=torch.cuda.Stream();center,_,truth=load_frame(root,scene,0)
        handle=context(stack,dll,center,truth['inverse_depth'],stream)
        check_cuda(dll.live_set_detail(handle,2));check_cuda(dll.live_set_disparity_budget(handle,0))
        check_cuda(dll.live_set_subpixel(handle,1));check_cuda(dll.live_set_coverage(handle,1))
        check_cuda(dll.live_set_window(handle,-1,1))
        pools={layout:stack.enter_context(LiveTexturePool(WIDTH,HEIGHT,diagnostic=True,layout=layout)) for layout in LAYOUTS}
        for frame in range(1,17):
            center,eyes,truth=load_frame(root,scene,frame)
            depth=np.ascontiguousarray(truth['inverse_depth'],np.float32)
            check_cuda(dll.live_post_source(handle,center.ctypes.data,depth.ctypes.data,0,1,.35,.04,.08,1,None,.008))
            for layout,pool in pools.items():
                pixels=read_pool(pool,handle,1/CONVERGENCE_Z,.9*WIDTH*BASELINE,frame%2,depth)
                actual=restored_eyes(pixels,layout,WIDTH,HEIGHT);expected=reference_eyes(eyes,layout)
                score=metrics.score(actual,expected,truth)
                rows[layout].append(dict(frame=frame,eyes=score))
                if frame==8:
                    cv2.imwrite(str(output/f'{scene}-truth-{layout}.png'),cv2.cvtColor(np.concatenate(expected,axis=1),cv2.COLOR_RGB2BGR))
                    cv2.imwrite(str(output/f'{scene}-known-depth-{layout}.png'),cv2.cvtColor(np.concatenate(actual,axis=1),cv2.COLOR_RGB2BGR))
                if frame==1:
                    duplicate=reference_eyes([center,center],layout)
                    control=dict(layout=layout,zero_stereo=metrics.score(duplicate,expected,truth),
                        swapped=metrics.score(expected[::-1],expected,truth))
                    controls.append(control)
                    oracle_edge=np.mean([e['regions']['edges']['mae'] for e in score])
                    zero_edge=np.mean([e['regions']['edges']['mae'] for e in control['zero_stereo']])
                    swapped_edge=np.mean([e['regions']['edges']['mae'] for e in control['swapped']])
                    interior=np.mean([e['regions']['visible_interior']['mae'] for e in score])
                    if not (interior<3 and oracle_edge<zero_edge and oracle_edge<swapped_edge):
                        raise ValueError(f'Camera/reference controls failed: {scene} {layout} {interior,oracle_edge,zero_edge,swapped_edge}')
    return dict(layouts={layout:dict(summary=summarize(values),rows=values) for layout,values in rows.items()},
                controls=controls,renderer_sha256=pin,
                settings=dict(subpixel=True,continuous_coverage=True,detail_mode=2,known_inverse_depth=True))


def dashboard(output,report):
    width,height=report.get('eye_size',[WIDTH,HEIGHT])
    lines=[report.get('title','# 최종 SBS 정답 영상 비교'),'',f"실행 상태: {'완료' if report['completed'] else '부분/실패'}",'',
        report.get('scope_text','독립적으로 렌더링한 중앙·좌우 카메라 장면 4개입니다. Spring 결과와 데이터·측정 목적이 다릅니다.'),
        '비교용 실행에서만 시차 압축과 창 가장자리 가림을 끄고, 별도 구간에서 카메라 보정을 한 번 수행했습니다.',
        '모델별 기본 후처리·실제 네이티브 출력은 유지합니다. 앱 기본 설정이나 실제 모니터의 편안함을 판정하는 수치는 아닙니다.','']
    entries=[];macro=[]
    for case in report['cases']:
        for layout,result in case['result']['layouts'].items():
            s=result['summary'];entries.append(dict(model=case['model'],scene=case['scene'],layout=layout,
                psnr_db=s['psnr_db'],ssim=s['ssim'],lpips=s['lpips'],rgb_mae=s['mae'],
                edge_mae=s['regions']['edges']['mae'],hidden_background_mae=s['regions']['disoccluded']['mae']))
    for layout in LAYOUTS:
        lines += [f'## {layout}','', '| 모델 | 완료 장면 수 | PSNR ↑ | SSIM ↑ | LPIPS ↓ | 경계 MAE ↓ | 가려진 배경 MAE ↓ |',
            '|---|---:|---:|---:|---:|---:|---:|']
        models=['known-depth']+list(report['models'])
        combined=entries+[dict(model='known-depth',scene=c['scene'],layout=layout,
            psnr_db=c['result']['layouts'][layout]['summary']['psnr_db'],ssim=c['result']['layouts'][layout]['summary']['ssim'],
            lpips=c['result']['layouts'][layout]['summary']['lpips'],edge_mae=c['result']['layouts'][layout]['summary']['regions']['edges']['mae'],
            hidden_background_mae=c['result']['layouts'][layout]['summary']['regions']['disoccluded']['mae']) for c in report['oracles']]
        for model in models:
            values=[r for r in combined if r['model']==model and r['layout']==layout]
            if not values:continue
            row=dict(model=model,layout=layout,scenes=len(values))
            for key in ('psnr_db','ssim','lpips','edge_mae','hidden_background_mae'):
                valid=[r[key] for r in values if r[key] is not None]
                row[key]=statistics.mean(valid) if valid else None
            macro.append(row)
            lines.append('| '+' | '.join([model,str(len(values))]+['N/A' if row[k] is None else f'{row[k]:.4f}' for k in ('psnr_db','ssim','lpips','edge_mae','hidden_background_mae')])+' |')
    report['macro']=macro
    paired=[]
    for layout in LAYOUTS:
        for a,b in itertools.combinations(report['models'],2):
            left={r['scene']:r for r in entries if r['model']==a and r['layout']==layout}
            right={r['scene']:r for r in entries if r['model']==b and r['layout']==layout}
            for metric in ('psnr_db','ssim','lpips','edge_mae','hidden_background_mae'):
                differences=[left[s][metric]-right[s][metric] for s in sorted(left.keys()&right.keys())
                    if left[s][metric] is not None and right[s][metric] is not None]
                if not differences:continue
                delta=np.asarray(differences);higher=metric in ('psnr_db','ssim')
                draws=np.random.default_rng(37).choice(delta,(10000,len(delta)),replace=True).mean(axis=1)
                paired.append(dict(layout=layout,a=a,b=b,metric=metric,higher_is_better=higher,scenes=len(delta),
                    a_wins=int((delta>0 if higher else delta<0).sum()),b_wins=int((delta<0 if higher else delta>0).sum()),
                    mean_a_minus_b=float(delta.mean()),exploratory_scene_bootstrap_95=np.quantile(draws,[.025,.975]).tolist()))
    report['paired']=paired
    lines+=['',report.get('reference_text','known-depth는 정답 깊이를 쓴 네이티브 렌더러 대조군입니다. 실제 좌우 정답은 별도 3D 광선 교차 계산으로 생성합니다.'),
        f'Half TB의 정답도 같은 축소·복원 규칙으로 처리한 뒤 논리적 눈별 {width}×{height}에서 비교합니다. 형식 간 숫자는 각각의 정답을 기준으로 합니다.',
        '전체 영역 점수와 물체 경계·중앙 시점에서 가려졌던 배경 영역 오차를 함께 봅니다. 모델별 가시성으로 평가 영역을 줄이지 않습니다.',
        report.get('calibration_text','카메라 보정은 정적 준비 구간에 고정하며, 평가 16프레임에는 다시 맞추지 않습니다. 종합 점수나 보편적 순위는 만들지 않습니다.'),'']
    (output/'summary.md').write_text('\n'.join(lines),encoding='utf-8')
    if entries:
        with (output/'cases.csv').open('w',newline='',encoding='utf-8') as handle:
            writer=csv.DictWriter(handle,fieldnames=list(entries[0]));writer.writeheader();writer.writerows(entries)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=ROOT/'out/sbs-rgb-fixture-20261110')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--model',action='append',choices=tuple(MODES))
    parser.add_argument('--noncommercial',action='store_true')
    parser.add_argument('--oracle-only',action='store_true')
    args=parser.parse_args();models=args.model or list(MODES)
    if not args.oracle_only and 'ovda-small-c16' in models and not args.noncommercial:raise ValueError('Confirm existing oVDA noncommercial scope')
    manifest=json.loads((args.source/'manifest.json').read_text())
    if (not manifest['completed'] or manifest['scenes']!=list(SCENES) or
            (manifest['width'],manifest['height'])!=(WIDTH,HEIGHT) or
            manifest['baseline_m']!=BASELINE or manifest['convergence_z_m']!=CONVERGENCE_Z or
            manifest['focal']!=.9*WIDTH):raise ValueError('Invalid analytic corpus camera contract')
    args.output.mkdir(parents=True,exist_ok=False)
    configure_resource_root(BUNDLE);cv2.setNumThreads(1)
    report=dict(completed=False,contract=CONTRACT,source_manifest_sha256=hashlib.sha256((args.source/'manifest.json').read_bytes()).hexdigest(),
        gpu=torch.cuda.get_device_name(),torch=torch.__version__,git_head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        git_dirty=bool(subprocess.check_output(['git','status','--porcelain'],text=True).strip()),models={},cases=[],oracles=[])
    (args.output/'protocol.json').write_text(json.dumps(CONTRACT,indent=2))
    try:
        for entry in manifest['files']:
            if hashlib.sha256((args.source/entry['path']).read_bytes()).hexdigest()!=entry['sha256']:raise ValueError('Fixture hash mismatch')
        metrics=Metrics();report['metric']=metrics.identity
        for scene in SCENES:
            result=oracle_scene(args.source,scene,metrics,args.output)
            report['oracles'].append(dict(scene=scene,result=result))
            dashboard(args.output,report);(args.output/'report.json').write_text(json.dumps(report,indent=2))
            print(scene,'independent camera / native known-depth controls passed',flush=True)
        if not args.oracle_only:
            for model in models:
                with ExitStack() as stack:
                    backend,owner,post,policy=open_session(stack,model,WIDTH,HEIGHT,'full-sbs',args.noncommercial)
                    half=stack.enter_context(LiveTexturePool(WIDTH,HEIGHT,diagnostic=True,layout='half-tb'))
                    report['models'][model]=model_identity(model,owner,policy,backend,post)
                    for scene in SCENES:
                        started=time.monotonic()
                        result=run_model_scene(model,scene,args.source,metrics,stack,backend,owner,post,policy,half,args.output)
                        report['cases'].append(dict(model=model,scene=scene,result=result))
                        dashboard(args.output,report);(args.output/'report.json').write_text(json.dumps(report,indent=2))
                        print(model,scene,'RGB case complete',round(time.monotonic()-started,2),flush=True)
                    report['models'][model]=model_identity(model,owner,policy,backend,post)
        report['completed']=True
    except BaseException as error:
        report['error']=repr(error);raise
    finally:
        dashboard(args.output,report);(args.output/'report.json').write_text(json.dumps(report,indent=2))


if __name__=='__main__':main()
