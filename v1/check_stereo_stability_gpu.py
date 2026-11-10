"""Independent subpixel oracle, occlusion checks and owned native/VFG parity.

Synthetic inputs only. Timings cover GPU projection, not capture or live FPS.
"""
import argparse
import ctypes as ct
from contextlib import ExitStack
import json
from pathlib import Path

import numpy as np
import torch

from check_stereo_geometry_gpu import load, context, check_cuda
from depthsbs_app.desktop_jobs import ROOT
from depthsbs_app.live_gpu_candidate import DLL_PATH, DLL_SHA256
from depthsbs_app.small_gpu_input import DLL_PATH as SMALL, DLL_SHA256 as SMALL_HASH
from depthsbs_app.live_texture_pool import LiveTexturePool
from depthsbs_app.stereo_stability import sample_depth


def project(dll, handle, frame, refined, convergence, scale):
    eyes = [np.empty_like(frame), np.empty_like(frame)]
    invalid = ct.c_int()
    check_cuda(dll.live_project(handle, refined.ctypes.data, convergence, scale, 1,
                               eyes[0].ctypes.data, eyes[1].ctypes.data, ct.byref(invalid)))
    assert not invalid.value
    return np.concatenate(eyes, axis=1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    from native_path import BRIDGE, BRIDGE_HASH, BridgePool
    dll = load(DLL_PATH, DLL_SHA256)
    small = load(SMALL, SMALL_HASH)
    prior = load(ROOT/'out/live-depth-stereo-lr/live_depth.dll',
                 'd60fde89efe1cebc1ae0599f5c0ed1ada51b54b5851aedd232774d4a4fb2a8f7')
    for library in (dll, small):
        library.live_set_subpixel.argtypes = [ct.c_void_p, ct.c_int]
        library.live_stereo_samples.argtypes = [ct.c_void_p, ct.c_void_p]
        library.live_projection_times.argtypes = [ct.c_void_p, ct.c_void_p]
        library.live_set_parallel.argtypes = [ct.c_void_p, ct.c_int]
    bridge = load(BRIDGE, BRIDGE_HASH)
    bridge.vfg_project.argtypes = [ct.c_void_p]*2+[ct.c_float]*2+[ct.c_int, ct.c_void_p]
    rows, errors = [], {0: [], 1: []}
    stream = torch.cuda.Stream()
    with ExitStack() as stack:
        frame = np.zeros((32, 256, 3), np.uint8)
        frame[:, 110:114, 0] = 255
        depth = np.full((32, 256), .7, np.float32)
        handle = context(stack, dll, frame, depth, stream)
        for enabled in (0, 1):
            check_cuda(dll.live_set_subpixel(handle, enabled))
            for shift in np.linspace(0, 2, 41):
                actual = project(dll, handle, frame, depth, .7-shift/10, 20)
                for eye, sign in ((0, 1), (1, -1)):
                    weights = actual[16, eye*256:(eye+1)*256, 0].astype(float)
                    center = np.dot(weights, np.arange(256))/weights.sum()
                    errors[enabled].append(float(center-(111.5+sign*shift)))
        assert max(map(abs, errors[1])) < .003
        assert max(map(abs, errors[0])) > .45
        # Zero disparity must be exact, including high-frequency texture.
        texture = np.random.default_rng(42).integers(0, 256, frame.shape, np.uint8)
        identity_handle = context(stack, dll, texture, depth, stream)
        check_cuda(dll.live_set_subpixel(identity_handle, 1))
        identity = project(dll, identity_handle, texture, depth, .7, 20)
        assert np.array_equal(identity, np.concatenate((texture, texture), axis=1))
        # A foreground red block over blue background may not mix surfaces.
        color = np.zeros_like(frame); color[:, :, 2] = 255; color[:, 80:150] = (255, 0, 0)
        layers = np.full(depth.shape, .2, np.float32); layers[:, 80:150] = .8
        layer_handle = context(stack, dll, color, layers, stream)
        check_cuda(dll.live_set_subpixel(layer_handle, 1))
        actual = project(dll, layer_handle, color, layers, .45, 20)
        assert not np.any((actual[:, :, 0] > 0) & (actual[:, :, 2] > 0))
    for width, height in ((17,16), (256,72), (1920,1080), (3840,2160)):
        frame = np.random.default_rng(42).integers(0, 256, (height,width,3), np.uint8)
        depth = np.broadcast_to(np.linspace(0,1,width,dtype=np.float32), (height,width)).copy()
        with ExitStack() as stack:
            handle = context(stack, dll, frame, depth, stream)
            check_cuda(dll.live_set_parallel(handle, 1))
            small_handle = context(stack, small, frame, depth, stream)
            old_handle = context(stack, prior, frame, depth, stream)
            reference = project(prior, old_handle, frame, depth, .45, width*.026)
            assert np.array_equal(reference, project(dll,handle,frame,depth,.45,width*.026))
            assert np.array_equal(reference, project(small,small_handle,frame,depth,.45,width*.026))
            check_cuda(dll.live_set_subpixel(handle, 1))
            check_cuda(small.live_set_subpixel(small_handle, 1))
            expected = project(dll,handle,frame,depth,.45,width*.026)
            assert np.array_equal(expected, project(small,small_handle,frame,depth,.45,width*.026))
            samples = np.empty((32,32),np.float32)
            check_cuda(dll.live_stereo_samples(handle,samples.ctypes.data))
            assert np.array_equal(samples, sample_depth(depth))
            pool = stack.enter_context(LiveTexturePool(width,height,diagnostic=True))
            native = np.empty((height,width*2,4),np.uint8)
            pool.check(pool.dll.live_pool_publish(pool.handle,handle,.45,width*.026,1,None,0,0))
            pool.check(pool.dll.live_pool_readback(pool.handle,0,native.ctypes.data))
            assert np.all(native[:,:,3] == 255) and np.array_equal(native[:,:,:3],expected)
            vfg_pool = stack.enter_context(BridgePool(width,height,diagnostic=True))
            with torch.cuda.stream(stream):
                pixels = torch.empty((height,width*2,4),dtype=torch.uint8,device='cuda')
            vfg_pool.check(bridge.vfg_project(handle,pixels.data_ptr(),.45,width*.026,1,None))
            with torch.cuda.stream(stream):
                actual = pixels.cpu().numpy()
            assert np.array_equal(actual,native)
            times = {0: [], 1: []}
            for repeat in range(14):
                for enabled in (repeat%2, 1-repeat%2):
                    check_cuda(dll.live_set_subpixel(handle,enabled))
                    vfg_pool.check(bridge.vfg_project(handle,pixels.data_ptr(),.45,width*.026,1,None))
                    stream.synchronize()
                    timing = np.zeros(6,np.float32)
                    check_cuda(dll.live_projection_times(handle,timing.ctypes.data))
                    if repeat >= 4:
                        times[enabled].append(float(timing.sum()))
            rows.append(dict(size=[width,height],reference_exact=True,small_exact=True,
                             native_vfg_exact=True,sample_exact=True,
                             gpu_projection_ms={str(k):float(np.median(v)) for k,v in times.items()}))
    report = dict(passed=True, centroid_max_error_px={str(k):max(map(abs,v)) for k,v in errors.items()},
                  identity_exact=True,occlusion_no_color_bleed=True,rows=rows,
                  scope='Synthetic GPU geometry and projection cost; not live FPS or physical comfort')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
