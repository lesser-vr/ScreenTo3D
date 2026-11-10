"""Read-only rendering review: deployed CUDA gates and offline motion candidate.

No app defaults, inference cadence, private capture or binary pins are changed.
Public residuals are proxies; the filtering and scoring flow presets differ.
The silhouette comparison deliberately retains reference/subpixel controls;
it does not enable the subsequently promoted coverage mode.
"""
import argparse
import ctypes as ct
from contextlib import ExitStack
import json
import os
from pathlib import Path
import time

import cv2
import numpy as np
import torch

from check_stereo_geometry_gpu import load, check_cuda, context
from check_stereo_stability_gpu import project
from depthsbs_app.da2_base import binding
from depthsbs_app.desktop_jobs import ROOT
from depthsbs_app.live_gpu_candidate import DLL_PATH, DLL_SHA256
from depthsbs_app.live_policy import resolve_live
from depthsbs_app.live_scene_history import LiveSceneHistory
from temporal_depth_experiment import align_history
from public_test_media import PublicFrames, SOURCES, ATTRIBUTION


def silhouette(dll, strength):
    """Known foreground shift straddles one pixel; measure its coverage edge."""
    frame = np.zeros((32,1920,3),np.uint8)
    frame[:,:,2] = 255
    frame[:,700:1200] = (255,0,0)
    depth = np.full(frame.shape[:2],.15,np.float32)
    stream = torch.cuda.Stream()
    edges = [[],[]]
    exact = []
    with ExitStack() as stack:
        handle = context(stack,dll,frame,depth,stream)
        scale = 1920*.026*strength
        shift_range = (10*strength-.05,10*strength+.05)
        for shift in np.linspace(*shift_range,21):
            depth[:,700:1200] = .45+2*shift/scale
            pair = []
            for enabled in (0,1):
                check_cuda(dll.live_set_subpixel(handle,enabled))
                result = project(dll,handle,frame,depth,.45,scale)
                pair.append(result)
                edges[enabled].append(int(np.flatnonzero(result[16,:1920,0]>127)[0]))
            exact.append(bool(np.array_equal(*pair)))
    assert all(exact)
    assert np.ptp(edges[1]) == 1
    return dict(strength=strength,input_shift_range=list(shift_range),reference_edges=edges[0],subpixel_edges=edges[1],
                output_exact_between_modes=True,measured_edge_jump_px=1,
                meaning='Texture reconstruction retains the hard foreground coverage boundary')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--silhouette-only',action='store_true')
    args = parser.parse_args()
    cv2.setNumThreads(1)
    torch.set_num_threads(4)
    dll = load(DLL_PATH,DLL_SHA256)
    dll.live_snapshot.argtypes = [ct.c_void_p]*4
    dll.live_set_subpixel.argtypes = [ct.c_void_p,ct.c_int]
    report = dict(passed=False,silhouette=[silhouette(dll,s) for s in (1.,.5)],clips=[],attribution=ATTRIBUTION,
                  scope='Offline review on public 1080p RGB, Base FP16 fresh each processed frame; no live FPS or physical viewing claim')
    if args.silhouette_only:
        report.update(passed=True,scope='Synthetic GPU coverage boundary at strengths 1.0 and 0.5 only')
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2))
        print('Both strengths retain a one-pixel coverage transition; reference/subpixel exact.')
        return
    policy = resolve_live('balanced')
    shape = (1080,1920)
    kernel = np.ones((7,7),np.uint8)
    xx,yy = np.meshgrid(np.arange(480,dtype=np.float32),np.arange(270,dtype=np.float32))
    with ExitStack() as stack:
        runtime = Path('C:/TensorRT/TensorRT-11.2.1.2/bin')
        stack.enter_context(os.add_dll_directory(str(runtime)))
        backend = binding(ROOT/'out/da2-base-local',runtime)
        backend.input_validator(dict(width=1920,height=1080))
        engine = stack.enter_context(backend.engine_factory(None))
        for name in SOURCES:
            with ExitStack() as scene_stack:
                handle = ct.c_void_p()
                check_cuda(dll.live_create(ct.byref(handle),1920,1080,engine.stream.cuda_stream))
                scene_stack.callback(lambda h=handle:check_cuda(dll.live_destroy(h)))
                aligned,normalized,smooth = [np.empty(shape,np.float32) for _ in range(3)]
                bounds = np.empty(2,np.float64)
                history = LiveSceneHistory(policy.scene_cut_threshold)
                previous_rgb = previous_smooth = previous_bounds = previous_small = previous_gray = previous_candidate = None
                fwd = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_FAST)
                bwd = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_FAST)
                scorer = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
                rows = []
                for index,rgb in enumerate(PublicFrames(name,180)):
                    if index%2:
                        continue
                    raw = np.ascontiguousarray(engine.infer(rgb)[0])
                    event = history.inspect(rgb)
                    reset = previous_rgb is None or event.cut or index == 90
                    check_cuda(dll.live_post_source(handle,rgb.ctypes.data,raw.ctypes.data,0,
                        policy.depth_guide_radius,policy.temporal_alpha,policy.temporal_color_threshold,
                        policy.temporal_depth_threshold,int(reset),aligned.ctypes.data,policy.temporal_depth_transition))
                    check_cuda(dll.live_snapshot(handle,normalized.ctypes.data,smooth.ctypes.data,bounds.ctypes.data))
                    small = cv2.resize(aligned,(480,270))
                    gray = cv2.resize(cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY),(480,270))
                    candidate = small.copy()
                    row = dict(frame=index,reset=bool(reset))
                    if not reset:
                        changed = np.max(np.abs(rgb.astype(np.int16)-previous_rgb.astype(np.int16)),axis=2)/255 > policy.temporal_color_threshold
                        changed = cv2.dilate(changed.astype(np.uint8),kernel)!=0
                        delta = np.abs(normalized-previous_smooth)
                        valid_ema = ~changed & (delta<policy.temporal_depth_threshold)
                        expected = np.where(valid_ema,
                            (policy.temporal_alpha+(1-policy.temporal_alpha)*np.clip((delta-.072)/.008,0,1))*normalized+
                            (1-policy.temporal_alpha)*(1-np.clip((delta-.072)/.008,0,1))*previous_smooth,normalized)
                        assert np.max(np.abs(expected-smooth)) < 2e-6
                        frozen = np.clip((raw-float(previous_bounds[0]))/max(float(np.diff(previous_bounds)[0]),1e-6),0,1)
                        bounds_effect = np.abs(normalized-frozen)*1920*policy.divergence
                        begun = time.perf_counter_ns()
                        forward = fwd.calc(previous_gray,gray,None)
                        backward = bwd.calc(gray,previous_gray,None)
                        candidate,accepted = align_history(small,previous_small,gray,previous_gray,forward,backward)
                        candidate_ms = (time.perf_counter_ns()-begun)/1e6
                        assert np.array_equal(candidate[~accepted],small[~accepted])
                        score_flow = scorer.calc(gray,previous_gray,None)
                        mx,my = xx+score_flow[:,:,0], yy+score_flow[:,:,1]
                        old_gray = cv2.remap(previous_gray,mx,my,cv2.INTER_LINEAR)
                        mask = (mx>1)&(mx<479)&(my>1)&(my<269)&(np.abs(gray.astype(float)-old_gray)<8)
                        edge = (cv2.dilate(small,np.ones((3,3),np.uint8))-cv2.erode(small,np.ones((3,3),np.uint8)))>.03
                        scores = {}
                        for label,current,previous in (('baseline',small,previous_small),('motion',candidate,previous_candidate)):
                            residual = np.abs(current-cv2.remap(previous,mx,my,cv2.INTER_LINEAR))*1920*policy.divergence
                            scores[label] = dict(mean=float(residual[mask].mean()),
                                edge=float(residual[mask&edge].mean()) if (mask&edge).any() else None)
                        row.update(motion_bypass_fraction=float(changed.mean()),
                            ema_eligible_fraction=float(valid_ema.mean()),
                            bounds_only_disparity_mae_px=float(bounds_effect.mean()),
                            bounds_only_disparity_p95_px=float(np.percentile(bounds_effect,95)),
                            accepted_fraction=float(accepted.mean()),candidate_ms=candidate_ms,
                            independent_flow_residual_px=scores,
                            edge_candidate_change_mae=float(np.abs(candidate-small)[edge].mean()) if edge.any() else 0)
                    else:
                        assert np.array_equal(candidate,small)
                    rows.append(row)
                    previous_rgb = rgb
                    previous_smooth,previous_bounds = smooth.copy(),bounds.copy()
                    previous_small,previous_gray,previous_candidate = small,gray,candidate
                    history.commit(event)
                measured = [r for r in rows if not r['reset']]
                summary = {key:float(np.mean([r[key] for r in measured])) for key in
                    ('motion_bypass_fraction','ema_eligible_fraction','bounds_only_disparity_mae_px','bounds_only_disparity_p95_px','accepted_fraction','candidate_ms','edge_candidate_change_mae')}
                summary['residual_px'] = {mode:{zone:float(np.mean([r['independent_flow_residual_px'][mode][zone] for r in measured if r['independent_flow_residual_px'][mode][zone] is not None])) for zone in ('mean','edge')} for mode in ('baseline','motion')}
                report['clips'].append(dict(name=name,summary=summary,frames=rows))
                print(json.dumps(dict(clip=name,**summary)),flush=True)
    report['passed'] = True
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
