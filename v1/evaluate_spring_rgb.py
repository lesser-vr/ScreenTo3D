"""Spring hold-out right-camera RGB from left input, complementing true three-view SBS tests."""
import argparse
from contextlib import ExitStack
from dataclasses import replace
import ctypes as ct
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import time
import cv2
import numpy as np
import torch

from evaluate_sbs_quality import open_session,Session,MODES
from evaluate_spring_quality import read_gt,model_identity
from evaluate_sbs_rgb import Metrics,LAYOUTS,read_pool,configure_camera_comparison,dashboard,summarize
from screento3d_app.desktop_jobs import ROOT,BUNDLE
from screento3d_app.resources import configure_resource_root
from screento3d_app.live_texture_pool import LiveTexturePool
from screento3d_app.spring_quality import fit_affine,truth_edges
from screento3d_app.sbs_rgb_quality import restored_eyes,reference_eyes

W,H=1920,1080
CONTRACT=dict(scope='Spring left-camera input -> held-out right-camera RGB; only right native eye scored, not full binocular reference',
    frames=dict(warmup=[1,32],calibration=[33,48],evaluation=[49,80]),
    source_hz=60,projection='right displacement = -GT positive disparity; calibration scale=2*a and convergence=-b/a',
    calibration='postprocessed projection depth -> GT source disparity OLS on fixed8px grid; fit only33-48 then freeze',
    benchmark_only_changes='disable nonlinear disparity compression and window masks for reference matching; retain model postprocessing and native rendering',
    mask='GT right disparity and GT left/right visibility, common fixed8row/16column crop; no prediction-dependent masks',
    truth='original independently rendered right-camera RGB, not RGB warped with tested depth',
    sampling='official GT [::2,::2], 1080p units; HalfTB target box-reduced and bilinearly restored',
    controls='known GT source disparity /128 and scale256; zero stereo duplicate source; GT NaNs in control only inpainted before native submission',
    metrics='PSNR GaussianRGB-SSIM LPIPS-Alex v0.1; edge and disocclusion RGB MAE',
    inference='ordered causal updates, no dropped frames; not an FPS/comfort result')


def rgb(root,scene,kind,index):
    bgr=cv2.imread(str(root/'spring/train'/scene/kind/f'{kind}_{index:04d}.png'))
    if bgr is None or bgr.shape!=(H,W,3):raise ValueError('Invalid Spring camera RGB')
    return np.ascontiguousarray(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB))


def target(root,scene,index):
    image=rgb(root,scene,'frame_right',index)
    left=read_gt(root,scene,'disp1_left',index);right=read_gt(root,scene,'disp1_right',index)
    yy,xx=np.indices(right.shape,dtype=np.float32);mx=xx+right
    sampled=cv2.remap(left,np.nan_to_num(mx,nan=-10),yy,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=float('nan'))
    valid=np.isfinite(right)&(right>=0);valid[:8]=False;valid[-8:]=False;valid[:,:16]=False;valid[:,-16:]=False
    inside=np.isfinite(mx)&(mx>=1)&(mx<W-2)&np.isfinite(sampled)
    visible=inside&(np.abs(sampled-right)<=.5)
    edge=truth_edges(right)
    masks=dict(right_all=valid,right_edges=valid&edge,right_disoccluded=valid&inside&~visible,
               right_visible_interior=valid&visible&~edge)
    return image,masks


def score_right(metrics,pixels,layout,truth,masks):
    actual=restored_eyes(pixels,layout,W,H)[1]
    reference=reference_eyes([truth,truth],layout)[1]
    return metrics.score([actual],[reference],masks,sides=('right',)),actual,reference


def oracle(root,scene,metrics,output):
    from check_stereo_geometry_gpu import load,context,check_cuda
    from screento3d_app.live_gpu_candidate import DLL_PATH,DLL_SHA256
    from screento3d_app.portable_cuda import binary
    path,pin=binary(DLL_PATH,DLL_SHA256);dll=load(path,pin)
    for name in ('live_set_detail','live_set_subpixel','live_set_coverage','live_set_disparity_budget'):
        getattr(dll,name).argtypes=[ct.c_void_p,ct.c_int]
    dll.live_set_window.argtypes=[ct.c_void_p,ct.c_double,ct.c_int]
    rows={k:[] for k in LAYOUTS};zeros={k:[] for k in LAYOUTS}
    with ExitStack() as stack:
        stream=torch.cuda.Stream();source=rgb(root,scene,'frame_left',49)
        depth=np.nan_to_num(read_gt(root,scene,'disp1_left',49)/128)
        handle=context(stack,dll,source,depth,stream)
        check_cuda(dll.live_set_detail(handle,2));check_cuda(dll.live_set_subpixel(handle,1));check_cuda(dll.live_set_coverage(handle,1))
        check_cuda(dll.live_set_disparity_budget(handle,0));check_cuda(dll.live_set_window(handle,-1,1))
        pools={k:stack.enter_context(LiveTexturePool(W,H,diagnostic=True,layout=k)) for k in LAYOUTS}
        for index in range(49,81):
            source=rgb(root,scene,'frame_left',index)
            disparity=read_gt(root,scene,'disp1_left',index)
            bad=~np.isfinite(disparity)
            if bad.any():disparity=cv2.inpaint(np.nan_to_num(disparity),bad.astype(np.uint8),3,cv2.INPAINT_NS)
            depth=np.ascontiguousarray(disparity/128,np.float32)
            check_cuda(dll.live_post_source(handle,source.ctypes.data,depth.ctypes.data,0,1,.35,.04,.08,1,None,.008))
            expected,masks=target(root,scene,index)
            for layout,pool in pools.items():
                pixels=read_pool(pool,handle,0,256,index%2,depth)
                scores,actual,reference=score_right(metrics,pixels,layout,expected,masks)
                rows[layout].append(dict(frame=index,eyes=scores))
                zero=reference_eyes([source,source],layout)[1]
                zeros[layout].append(dict(frame=index,eyes=metrics.score([zero],[reference],masks,sides=('right',))))
                if index==64:
                    cv2.imwrite(str(output/f'{scene}-known-depth-{layout}.png'),cv2.cvtColor(actual,cv2.COLOR_RGB2BGR))
                    cv2.imwrite(str(output/f'{scene}-truth-{layout}.png'),cv2.cvtColor(reference,cv2.COLOR_RGB2BGR))
    return dict(layouts={k:dict(summary=summarize(v),rows=v) for k,v in rows.items()},
                zero_controls={k:summarize(v) for k,v in zeros.items()},renderer_sha256=pin)


def model_scene(model,scene,root,metrics,backend,owner,post,policy,half,output):
    configure_camera_comparison(post);post.policy=policy;post.stereo_convergence=policy.convergence
    session=Session(backend,owner,post,policy,model)
    samples=[];targets=[];rows={k:[] for k in LAYOUTS};resets=[];fit=None
    for index in range(1,81):
        source=rgb(root,scene,'frame_left',index)
        full,_,reason=session.frame(source,index-1)
        if reason:resets.append(dict(frame=index,reason=reason))
        if 33<=index<=48:
            depth=np.empty((H,W),np.float32)
            post._check(post.dll.live_detail_snapshot(post.handle,depth.ctypes.data))
            truth=read_gt(root,scene,'disp1_left',index)[4::8,4::8]
            valid=np.isfinite(truth)&(truth>=0)
            samples.append(depth[4::8,4::8][valid]);targets.append(truth[valid])
            if index==48:
                fit=fit_affine(samples,targets);scale=2*fit['scale'];convergence=-fit['offset']/fit['scale']
                if not np.isfinite(scale+convergence) or scale<1:raise ValueError('Invalid Spring camera calibration')
                post.policy=replace(policy,divergence=scale/W);post.stereo_convergence=convergence
        if index<49:continue
        if reason:raise ValueError('Reset in scored Spring RGB frames')
        expected,masks=target(root,scene,index)
        half_pixels=read_pool(half,post.handle,convergence,scale,index%2)
        for layout,pixels in zip(LAYOUTS,(full,half_pixels)):
            scores,actual,_=score_right(metrics,pixels,layout,expected,masks)
            rows[layout].append(dict(frame=index,eyes=scores))
            if index==64:cv2.imwrite(str(output/f'{scene}-{model}-{layout}.png'),cv2.cvtColor(actual,cv2.COLOR_RGB2BGR))
    return dict(calibration=dict(**fit,projection_scale=scale,convergence=convergence),resets=resets,
                layouts={k:dict(summary=summarize(v),rows=v) for k,v in rows.items()})


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,default=ROOT/'out/spring-source')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--noncommercial',action='store_true')
    args=p.parse_args()
    if not args.noncommercial:raise ValueError('Confirm existing oVDA noncommercial scope')
    manifests=[json.loads((args.source/name).read_text()) for name in ('manifest.json','right-manifest.json')]
    if not all(m['completed'] for m in manifests):raise ValueError('Incomplete Spring right-camera data')
    args.output.mkdir(parents=True,exist_ok=False);configure_resource_root(BUNDLE);cv2.setNumThreads(1)
    report=dict(completed=False,title='# Spring 오른쪽 정답 영상 비교',eye_size=[W,H],contract=CONTRACT,
        scope_text='Spring 왼쪽 입력으로 만든 오른쪽 눈 영상을 실제 오른쪽 카메라 정답과 비교합니다. 양눈 전체 정답 평가는 별도 3D 시험 결과에 있습니다.',
        calibration_text='33–48프레임에서 한 번 보정하고 49–80프레임에서는 고정합니다. 모델은 왼쪽 영상만 입력받으며 오른쪽 RGB는 평가 정답으로만 사용합니다.',
        reference_text='known-depth는 Spring 왼쪽 정답 시차를 쓴 네이티브 대조군입니다. 오른쪽 정답은 원본 Spring의 다른 카메라 영상이며, 생성 모델 입력이나 보정에 사용하지 않습니다.',
        gpu=torch.cuda.get_device_name(),torch=torch.__version__,models={},cases=[],oracles=[],
        sequences=manifests[0]['plan']['sequences'],attribution=manifests[0]['attribution'],
        source_manifests_sha256=[hashlib.sha256((args.source/name).read_bytes()).hexdigest() for name in ('manifest.json','right-manifest.json')],
        git_head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip())
    (args.output/'protocol.json').write_text(json.dumps(CONTRACT,indent=2))
    try:
        for manifest in manifests:
            for entry in manifest['entries']:
                if hashlib.sha256((args.source/entry['path']).read_bytes()).hexdigest()!=entry['sha256']:raise ValueError('Spring camera checksum mismatch')
        metrics=Metrics();report['metric']=metrics.identity
        for scene in report['sequences']:
            result=oracle(args.source,scene,metrics,args.output)
            report['oracles'].append(dict(scene=scene,result=result))
            dashboard(args.output,report);(args.output/'report.json').write_text(json.dumps(report,indent=2))
            print('Spring known-depth right-view',scene,'complete',flush=True)
        for model in MODES:
            with ExitStack() as stack:
                backend,owner,post,policy=open_session(stack,model,W,H,'full-sbs',True)
                half=stack.enter_context(LiveTexturePool(W,H,diagnostic=True,layout='half-tb'))
                report['models'][model]=model_identity(model,owner,policy,backend,post)
                for scene in report['sequences']:
                    started=time.monotonic();result=model_scene(model,scene,args.source,metrics,backend,owner,post,policy,half,args.output)
                    report['cases'].append(dict(model=model,scene=scene,result=result))
                    dashboard(args.output,report);(args.output/'report.json').write_text(json.dumps(report,indent=2))
                    print(model,scene,'Spring RGB complete',round(time.monotonic()-started,2),flush=True)
                report['models'][model]=model_identity(model,owner,policy,backend,post)
        report['completed']=True
    except BaseException as error:report['error']=repr(error);raise
    finally:dashboard(args.output,report);(args.output/'report.json').write_text(json.dumps(report,indent=2))


if __name__=='__main__':main()
