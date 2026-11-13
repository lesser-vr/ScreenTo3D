"""Same-depth GPU disparity contract; public clips are proxies, not viewing QA."""
import argparse
from contextlib import ExitStack
import ctypes as ct
import json
import os
from pathlib import Path

import cv2
import numpy as np
import torch

from check_stereo_geometry_gpu import load, context, check_cuda
from check_stereo_stability_gpu import project
from check_stereo_window import setup as window_setup, settings, state
from check_depth_range import allocate, post
from screento3d_app.desktop_jobs import ROOT, BUNDLE
from screento3d_app.live_gpu_candidate import DLL_PATH, DLL_SHA256
from screento3d_app.live_policy import resolve_live
from screento3d_app.live_scene_history import LiveSceneHistory
from screento3d_app.motion_history import MotionHistory
from screento3d_app.live_texture_pool import LiveTexturePool
from public_test_media import PublicFrames, SOURCES, ATTRIBUTION

OLD = ROOT / 'out/live-depth-window/live_depth.dll'
OLD_HASH = '141985fed439632197b907f50d34d9962b08fa6f36871e6221c3acc52d6e0fef'


def setup():
    dll = window_setup(load(DLL_PATH, DLL_SHA256))
    dll.live_set_disparity_budget.argtypes = [ct.c_void_p, ct.c_int]
    dll.live_shift_snapshot.argtypes = [ct.c_void_p, ct.c_void_p]
    return dll


def oracle(disparity, width):
    # Float64 independent signed total-disparity formula, not half-shift code.
    d = np.asarray(disparity, dtype=np.float64)
    knee = np.where(d >= 0, .0025, .0035) * width
    cap = np.where(d >= 0, .006, .008) * width
    excess = np.maximum(np.abs(d) - knee, 0)
    mapped = knee + (cap-knee) - (cap-knee)**2 / (cap-knee+excess)
    return np.where(np.abs(d) <= knee, d, np.sign(d)*mapped)


def disparity(dll, handle, shape):
    result = np.empty(shape, np.float32)
    check_cuda(dll.live_shift_snapshot(handle, result.ctypes.data))
    # Projection leaves the scratch shift negated for its final (right) eye.
    return result * -2


def validate(before, after, width):
    np.testing.assert_allclose(after, oracle(before, width), rtol=0, atol=4e-5)
    assert np.all(np.abs(after) <= np.abs(before) + 4e-5)
    assert np.array_equal(np.sign(before), np.sign(after))
    core = np.abs(before) <= np.where(before >= 0, .0025, .0035)*width
    assert np.array_equal(before[core], after[core])
    assert np.all(after <= width*.006+1e-5)
    assert np.all(after >= -width*.008-1e-5)


def summarize(before, after):
    height, width = before.shape
    center = (slice(height//3, height*2//3), slice(width//3, width*2//3))
    return dict(abs_disparity_px=[np.percentile(np.abs(d), [50,95,100]).tolist()
                                 for d in (before, after)],
                center_abs_px=[np.percentile(np.abs(d[center]), [50,95]).tolist()
                               for d in (before, after)],
                compressed_fraction=float(np.mean(np.abs(after-before) > 1e-5)))


def synthetic(dll):
    prior = window_setup(load(OLD, OLD_HASH))
    stream = torch.cuda.Stream()
    rows = []
    for width, height in ((16,16),(64,32),(1920,1080),(3440,1440),
                          (1080,1920),(3840,2160),(4096,2160)):
        rgb = np.random.default_rng(23).integers(0,256,(height,width,3),np.uint8)
        depth = np.broadcast_to(np.linspace(0,1,width,dtype=np.float32),
                                (height,width)).copy()
        with ExitStack() as stack:
            handle = context(stack,dll,rgb,depth,stream)
            old = context(stack,prior,rgb,depth,stream)
            for lib,h in ((dll,handle),(prior,old)):
                settings(lib,h)
                check_cuda(lib.live_set_window(h,1/60,1))
            pool = stack.enter_context(LiveTexturePool(width,height,diagnostic=True))
            for strength in (.25,.5,2):
                scale = width*.026*strength
                check_cuda(dll.live_set_disparity_budget(handle,0))
                check_cuda(dll.live_set_window(handle,1/60,1))
                before_rgb = project(dll,handle,rgb,depth,.45,scale)
                before = disparity(dll,handle,depth.shape)
                check_cuda(prior.live_set_window(old,1/60,1))
                assert np.array_equal(before_rgb,project(prior,old,rgb,depth,.45,scale))
                check_cuda(dll.live_set_disparity_budget(handle,1))
                check_cuda(dll.live_set_window(handle,1/60,1))
                after_rgb = project(dll,handle,rgb,depth,.45,scale)
                after = disparity(dll,handle,depth.shape)
                validate(before,after,width)
                assert np.all(np.diff(after[0]) > 0), 'Depth ordering lost'
                # Edge protection must follow the actual compressed shift.
                x = np.arange(width)[None,:]
                expected = [float(np.max(np.where((after>0)&(dist<after*.5),
                                                   np.minimum(after,width*.015),0)))
                            for dist in (x,width-1-x)]
                np.testing.assert_allclose(state(dll,handle)[:2],expected,atol=2e-5)
                pool.check(pool.dll.live_pool_publish(pool.handle,handle,.45,scale,1,None,0,0))
                native = np.empty((height,width*2,4),np.uint8)
                pool.check(pool.dll.live_pool_readback(pool.handle,0,native.ctypes.data))
                assert np.array_equal(native[:,:,:3],after_rgb)
                assert np.all(native[:,:,3] == 255)
                rows.append(dict(size=[width,height],strength=strength,
                                 native_exact=True,disabled_exact=True,**summarize(before,after)))
            assert dll.live_set_disparity_budget(handle,2) != 0
            assert dll.live_set_disparity_budget(None,1) != 0
            # GPU finite-difference changes: no temporal state, no amplification.
            previous = after
            previous_depth = depth.copy()
            for offset in (.001,-.002,.003,0):
                depth = np.clip(previous_depth+offset,0,1).astype(np.float32)
                project(dll,handle,rgb,depth,.45,scale)
                current = disparity(dll,handle,depth.shape)
                assert np.all(np.abs(current-previous) <=
                              np.abs(depth-previous_depth)*scale+5e-5)
                previous,previous_depth = current,depth.copy()
    # Actual image centroids establish eye direction independently of shift data.
    for level in (.05,.45,.95):
        rgb = np.zeros((32,512,3),np.uint8)
        rgb[:,254:258] = 255
        depth = np.full((32,512),level,np.float32)
        with ExitStack() as stack:
            handle = context(stack,dll,rgb,depth,stream)
            settings(dll,handle)
            check_cuda(dll.live_set_disparity_budget(handle,1))
            output = project(dll,handle,rgb,depth,.45,512*.013)
            centers = []
            for eye in range(2):
                weights = output[16,eye*512:(eye+1)*512,0].astype(float)
                centers.append(float(np.dot(weights,np.arange(512))/weights.sum()))
            expected = float(oracle((np.float32(level)-np.float32(.45))*(512*.013),512))
            assert abs(centers[0]-centers[1]-expected) < .01
            if level==.45:
                assert np.array_equal(output,np.concatenate((rgb,rgb),axis=1))
    return dict(cases=rows,centroid_eye_order=True,screen_plane_exact=True,
                fixed_setting_temporal_contraction=True)


def public(dll, model):
    policy = resolve_live('balanced' if model=='base' else 'performance',strength=.5)
    results = []
    with ExitStack() as stack:
        runtime = Path('C:/TensorRT/TensorRT-11.2.1.2/bin')
        stack.enter_context(os.add_dll_directory(str(runtime)))
        if model=='base':
            from screento3d_app.da2_base import binding
            backend = binding(ROOT/'out/da2-base-local',runtime)
            backend.input_validator(dict(width=1920,height=1080))
            engine = stack.enter_context(backend.engine_factory(None))
            stream = engine.stream
        else:
            from screento3d_app.resources import configure_resource_root
            from screento3d_app.small_gpu_input import SmallGpuCaptureEngine
            from screento3d_app.pipeline import preprocess
            configure_resource_root(BUNDLE)
            engine = stack.enter_context(SmallGpuCaptureEngine())
            stream = engine.torch_stream
        for name in SOURCES:
            with ExitStack() as scene:
                handle = allocate(scene,dll,1920,1080,stream.cuda_stream)
                settings(dll,handle)
                motion = scene.enter_context(MotionHistory(1920,1080,stream.cuda_stream,
                                                          DLL_SHA256,diagnostic=True))
                history = LiveSceneHistory(policy.scene_cut_threshold)
                previous = None
                rows = []
                for index,rgb in enumerate(PublicFrames(name,90)):
                    raw = (np.ascontiguousarray(engine.infer(rgb)[0]) if model=='base'
                           else cv2.resize(engine.infer(preprocess(rgb)).squeeze(),
                                           (1920,1080),interpolation=cv2.INTER_CUBIC))
                    event = history.inspect(rgb)
                    reset = index in (0,45) or event.cut
                    post(dll,handle,rgb,raw,policy,reset,1/60)
                    motion.apply(handle,1_000_000_000+index*16_666_667,reset=reset)
                    depth = motion.snapshot(handle)[0]
                    pair = []
                    for enabled in (0,1):
                        check_cuda(dll.live_set_disparity_budget(handle,enabled))
                        # Reset mask per projection for this same-depth comparison.
                        check_cuda(dll.live_set_window(handle,1/60,1))
                        project(dll,handle,rgb,depth,policy.convergence,1920*policy.divergence)
                        pair.append(disparity(dll,handle,depth.shape))
                    validate(*pair,1920)
                    row = dict(frame=index,reset=bool(reset),**summarize(*pair))
                    if previous is not None and not reset:
                        deltas = [np.abs(now-old) for now,old in zip(pair,previous)]
                        assert np.all(deltas[1] <= deltas[0]+5e-5)
                        row['same_pixel_delta_px'] = [np.percentile(d,[50,95,100]).tolist()
                                                      for d in deltas]
                    previous = pair
                    rows.append(row)
                    history.commit(event)
                summary = dict(model=model,clip=name,frames=len(rows),
                    mean_abs_disparity_px=np.mean([r['abs_disparity_px'] for r in rows],axis=0).tolist(),
                    mean_center_abs_px=np.mean([r['center_abs_px'] for r in rows],axis=0).tolist(),
                    mean_temporal_delta_px=np.mean([r['same_pixel_delta_px'] for r in rows
                                                   if 'same_pixel_delta_px' in r],axis=0).tolist())
                print(json.dumps(summary),flush=True)
                results.append(dict(summary=summary,rows=rows))
    return results


def benchmark(dll):
    stream = torch.cuda.Stream()
    rows = []
    for width,height in ((1920,1080),(3840,2160)):
        rgb = cv2.resize(PublicFrames('FloorballGame',1)[0],(width,height))
        depth = np.full((height,width),.95,np.float32)
        with ExitStack() as stack:
            handle = context(stack,dll,rgb,depth,stream)
            settings(dll,handle)
            check_cuda(dll.live_set_window(handle,1/60,1))
            project(dll,handle,rgb,depth,.45,width*.013)
            pool = stack.enter_context(LiveTexturePool(width,height,diagnostic=True))
            readback = np.empty((height,width*2,4),np.uint8)
            times = {0:[],1:[]}
            for iteration in range(60):
                for enabled in ((0,1) if iteration%2 else (1,0)):
                    check_cuda(dll.live_set_disparity_budget(handle,enabled))
                    start,end = torch.cuda.Event(enable_timing=True),torch.cuda.Event(enable_timing=True)
                    start.record(stream)
                    pool.check(pool.dll.live_pool_publish(pool.handle,handle,.45,width*.013,1,None,0,0))
                    end.record(stream)
                    end.synchronize()
                    if iteration>=10:
                        times[enabled].append(start.elapsed_time(end))
                    pool.check(pool.dll.live_pool_readback(pool.handle,0,readback.ctypes.data))
            rows.append(dict(size=[width,height],samples=50,
                             median_ms=[float(np.median(times[k])) for k in (0,1)],
                             p95_ms=[float(np.percentile(times[k],95)) for k in (0,1)]))
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--model',choices=('base','small'))
    parser.add_argument('--benchmark',action='store_true')
    args = parser.parse_args()
    cv2.setNumThreads(1)
    torch.set_num_threads(4)
    dll = setup()
    result = dict(dll=DLL_SHA256,passed=False)
    if args.model:
        result.update(public=public(dll,args.model),attribution=ATTRIBUTION)
    elif args.benchmark:
        result['benchmark'] = benchmark(dll)
    else:
        result['synthetic'] = synthetic(dll)
    result['passed'] = True
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2))
    print('Passed',flush=True)


if __name__=='__main__':
    main()
