"""Paired public-video depth history with identical Base FP16 inference.

Input delivery intentionally selects every second 60 Hz frame. No WGC/display
timing is inferred from this test. Motion error is a proxy, not depth truth.
"""
import argparse
import ctypes as ct
from contextlib import ExitStack
import json
import os
from pathlib import Path

import cv2
import numpy as np
import torch

from check_stereo_geometry_gpu import load, check_cuda
from screento3d_app.da2_base import binding
from screento3d_app.desktop_jobs import ROOT
from screento3d_app.live_gpu_candidate import DLL_PATH, DLL_SHA256
from screento3d_app.live_policy import resolve_live
from screento3d_app.live_scene_history import LiveSceneHistory
from screento3d_app.live_sbs import reset_reason
from screento3d_app.stereo_stability import ScreenPlane, sample_depth
from public_test_media import PublicFrames, SOURCES, ATTRIBUTION


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    cv2.setNumThreads(1)
    torch.set_num_threads(4)
    dll = load(DLL_PATH, DLL_SHA256)
    policy = resolve_live('balanced')
    shape = (1080,1920)
    rows = []
    with ExitStack() as stack:
        runtime = Path('C:/TensorRT/TensorRT-11.2.1.2/bin')
        stack.enter_context(os.add_dll_directory(str(runtime)))
        backend = binding(ROOT/'out/da2-base-local',runtime)
        backend.input_validator(dict(width=shape[1],height=shape[0]))
        engine = stack.enter_context(backend.engine_factory(None))
        for name in SOURCES:
            with ExitStack() as scene_stack:
                handles = []
                for _ in range(2):
                    handle = ct.c_void_p()
                    check_cuda(dll.live_create(ct.byref(handle),shape[1],shape[0],engine.stream.cuda_stream))
                    scene_stack.callback(lambda h=handle:check_cuda(dll.live_destroy(h)))
                    handles.append(handle)
                previous = [None,None]
                history = LiveSceneHistory(policy.scene_cut_threshold)
                tracker = ScreenPlane()
                resets = [0,0]
                errors = [[],[]]
                center_disparity = [[],[]]
                whole_disparity = [[],[]]
                anchors, rates, cut_parity = [],[],[]
                prior_gray = None
                flow_engine = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_FAST)
                xx, yy = np.meshgrid(np.arange(480,dtype=np.float32),np.arange(270,dtype=np.float32))
                for index,rgb in enumerate(PublicFrames(name,180)):
                    if index % 2:
                        continue
                    raw = np.ascontiguousarray(engine.infer(rgb)[0])
                    event = history.inspect(rgb)
                    # A forced cut halfway validates that no prior history survives.
                    cut = event.cut or index == 90
                    aligned = []
                    stamp = 1_000_000_000 + round(index*1e9/60)
                    for mode,handle in enumerate(handles):
                        reason = reset_reason(None if index == 0 else index-2,index,shape,shape,cut,
                            previous_source_ns=None if index == 0 else 1_000_000_000+round((index-2)*1e9/60),
                            source_ns=stamp,allow_coalescing=bool(mode))
                        resets[mode] += reason is not None
                        depth = np.empty(shape,np.float32)
                        check_cuda(dll.live_post_source(handle,rgb.ctypes.data,raw.ctypes.data,0,
                            policy.depth_guide_radius,policy.temporal_alpha,policy.temporal_color_threshold,
                            policy.temporal_depth_threshold,int(reason is not None),depth.ctypes.data,
                            policy.temporal_depth_transition))
                        engine.stream.synchronize()
                        assert np.isfinite(depth).all()
                        aligned.append(depth)
                    if cut:
                        cut_parity.append(bool(np.array_equal(*aligned)))
                    anchor = tracker.update(sample_depth(aligned[1]),stamp,reset=cut or index==0)
                    if anchors and not cut:
                        rates.append(abs(anchor-anchors[-1])*30)
                    anchors.append(anchor)
                    for mode,convergence in enumerate((policy.convergence,anchor)):
                        disparity = (aligned[1]-convergence)*shape[1]*policy.divergence
                        center_disparity[mode].append(float(np.median(np.abs(disparity[270:810,480:1440]))))
                        whole_disparity[mode].append(float(np.quantile(np.abs(disparity),.95)))
                    gray = cv2.resize(cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY),(480,270))
                    small = [cv2.resize(d,(480,270)) for d in aligned]
                    if prior_gray is not None and not cut:
                        flow = flow_engine.calc(gray,prior_gray,None)
                        mx, my = xx+flow[:,:,0], yy+flow[:,:,1]
                        old_gray = cv2.remap(prior_gray,mx,my,cv2.INTER_LINEAR)
                        mask = (mx>=1)&(mx<479)&(my>=1)&(my<269)&(np.abs(gray.astype(float)-old_gray)<8)
                        if mask.sum() > 1000:
                            for mode in range(2):
                                warped = cv2.remap(previous[mode],mx,my,cv2.INTER_LINEAR)
                                errors[mode].append(float(np.mean(np.abs(small[mode]-warped)[mask])))
                    previous,prior_gray = small,gray
                    history.commit(event)
                assert cut_parity and all(cut_parity)
                assert max(rates) <= .060001
                row = dict(clip=name,frames=len(anchors),resets=dict(legacy=resets[0],continuous=resets[1]),
                    flow_aligned_depth_mae=dict(legacy=float(np.mean(errors[0])),continuous=float(np.mean(errors[1]))),
                    central_abs_disparity_px=dict(fixed=float(np.mean(center_disparity[0])),anchor=float(np.mean(center_disparity[1]))),
                    whole_p95_abs_disparity_px=dict(fixed=float(np.mean(whole_disparity[0])),anchor=float(np.mean(whole_disparity[1]))),
                    convergence_range=[min(anchors),max(anchors)],max_convergence_rate=max(rates),cut_exact=True)
                rows.append(row)
                print(json.dumps(row),flush=True)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(dict(passed=True,rows=rows,attribution=ATTRIBUTION,
        scope='Three 3-second public clips, 30 Hz coalesced delivery, Base FP16; flow-aligned error is a temporal proxy, not ground truth or physical comfort'),indent=2))


if __name__ == '__main__':
    main()
