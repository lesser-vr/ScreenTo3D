"""Real CUDA Small resize/normalization and native output comparison."""
import argparse
import ctypes as ct
import json
from pathlib import Path

import cv2
import numpy as np
import torch

from depthsbs_app.desktop_jobs import BUNDLE
from depthsbs_app.resources import configure_resource_root
from depthsbs_app.small_gpu_input import SmallGpuCaptureEngine, cubic_coefficients
from depthsbs_app.live_small_gpu_input import LiveSmallGpuInput, LiveSmallGpuInputTexture
from depthsbs_app.live_gpu_candidate import LiveGpuCandidate
from depthsbs_app.gpu_frame import GpuFrame
from depthsbs_app.live_policy import resolve_live
from depthsbs_app.trt_backend import _cuda, cudart
from public_test_media import PublicFrames


def read_device(pointer, shape, stream):
    result = np.empty(shape, np.float32)
    _cuda(cudart.cudaMemcpyAsync(result.ctypes.data, pointer, result.nbytes,
        cudart.cudaMemcpyKind.cudaMemcpyDeviceToHost, stream))
    _cuda(cudart.cudaStreamSynchronize(stream))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--quality', choices=('reference','subpixel','coverage','range','motion','window','budget','detail'), default='reference')
    parser.add_argument('--strength', type=float, default=.25)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    configure_resource_root(BUNDLE)
    cv2.setNumThreads(1)
    torch.set_num_threads(1)
    report = dict(passed=False, quality=args.quality, strength=args.strength, preprocessing=[], product=[], limits=dict(
        resize_max=0, normalized_depth_mae=0,
        normalized_depth_max=0, sbs_rgb_mae=0, sbs_pixel_over1_fraction=0))
    rng = np.random.default_rng(721)
    policy = resolve_live('performance',strength=args.strength)
    try:
        with SmallGpuCaptureEngine() as engine:
            lib = engine.gpu_input.dll
            lib.small_resize.argtypes = [ct.c_void_p, ct.c_size_t, ct.c_int, ct.c_int,
                                        ct.c_int, ct.c_void_p, ct.c_void_p, ct.c_void_p]
            for w, h in [(16,16),(17,21),(65,63),(518,518),(1920,1080),
                         (3440,1440),(1080,1920),(3840,2160),(4096,2160)]:
                with torch.cuda.stream(engine.torch_stream):
                    coefficients = torch.from_numpy(cubic_coefficients(w,h)).cuda()
                for pattern in ('random','gradient','flat'):
                    frame = rng.integers(0,256,(h,w,3),dtype=np.uint8)
                    if pattern == 'gradient': frame[:] = np.linspace(0,255,w,dtype=np.uint8)[None,:,None]
                    if pattern == 'flat': frame[:] = (19,128,242)
                    expected = cv2.resize(frame,(518,518),interpolation=cv2.INTER_CUBIC)
                    with torch.cuda.stream(engine.torch_stream):
                        source = torch.from_numpy(frame).cuda()
                        resized = torch.empty((518,518,3),dtype=torch.uint8,device='cuda')
                        assert lib.small_resize(source.data_ptr(),source.stride(0),w,h,3,
                            resized.data_ptr(),int(engine.stream),coefficients.data_ptr()) == 0
                        actual = resized.cpu().numpy()
                        bgra = np.zeros((h,w+8,4),np.uint8)
                        bgra[:,:w,:3] = frame[:,:,::-1]
                        pitched = torch.from_numpy(bgra).cuda()[:,:w]
                        assert lib.small_resize(pitched.data_ptr(),pitched.stride(0),w,h,4,
                            resized.data_ptr(),int(engine.stream),coefficients.data_ptr()) == 0
                        assert np.array_equal(actual,resized.cpu().numpy())
                    diff = np.abs(actual.astype(int)-expected.astype(int))
                    row = dict(size=[w,h],pattern=pattern,max=int(diff.max()),
                               changed_fraction=float(np.mean(diff!=0)))
                    report['preprocessing'].append(row)
                    assert row['max'] == 0, row
                    assert np.array_equal(engine.gpu_input.thumbnail(source),cv2.resize(frame,(32,32)))
            frames = [(name, index, PublicFrames(name, 360)[offset])
                      for name in ('FloorballGame','OfficeWalk','ParkingGarage')
                      for index, offset in enumerate((0,60,120,180,240,300))]
            for w,h in [(1920,1080),(3440,1440),(1080,1920),(3840,2160)]:
                with LiveGpuCandidate(w,h,policy,engine) as old, \
                     LiveSmallGpuInput(w,h,policy,engine) as gpu, \
                     LiveSmallGpuInput(w,h,policy,engine) as same_input, \
                     LiveSmallGpuInputTexture(w,h,policy,engine,diagnostic=True) as native:
                    for renderer in (old,gpu,same_input,native):
                        renderer.configure_live_quality(args.quality)
                    readback = np.empty((h,w*2,4),np.uint8)
                    for source, index, image in frames:
                        for renderer in (old,gpu,same_input,native):
                            renderer.source_ns = 1_000_000_000 + len(report['product']) * 33_333_333
                        frame = cv2.resize(image,(w,h))
                        if index==3: frame = 255-frame
                        if index==5:
                            frame[:] = 112
                            cv2.rectangle(frame,(w//3,h//3),(w*2//3,h*2//3),(180,80,50),-1)
                        with torch.cuda.stream(engine.torch_stream):
                            owned = GpuFrame(torch.from_numpy(cv2.cvtColor(frame,cv2.COLOR_RGB2BGRA)).cuda(),engine)
                        token = old.infer(frame)
                        expected_input = read_device(engine.device_input,(1,3,518,518),engine.stream)
                        expected_depth = read_device(token.pointer,token.shape,engine.stream)
                        expected = old.render(frame,token)
                        # Isolate postprocessing: old CPU resize, new GPU RGB delivery.
                        exact = same_input.render(owned,old.infer(frame))
                        assert np.array_equal(exact,expected), 'Postprocessing changed'
                        token = gpu.infer(owned)
                        actual_input = read_device(engine.device_input,(1,3,518,518),engine.stream)
                        actual_depth = read_device(token.pointer,token.shape,engine.stream)
                        actual = gpu.render(owned,token)
                        native.slot = index%2
                        slot = native.render(owned,native.infer(owned))
                        native.pool.check(native.pool.dll.live_pool_readback(native.pool.handle,slot,readback.ctypes.data))
                        assert np.array_equal(actual,readback[:,:,:3]) and np.all(readback[:,:,3]==255)
                        depth = np.abs(actual_depth-expected_depth)/max(float(np.ptp(expected_depth)),1e-6)
                        pixel = np.abs(actual.astype(np.int16)-expected.astype(np.int16))
                        row = dict(size=[w,h],source=source,frame=index,post_exact=True,native_exact=True,
                            input_max=float(np.abs(actual_input-expected_input).max()),
                            normalized_depth_mae=float(depth.mean()),normalized_depth_max=float(depth.max()),
                            sbs_rgb_mae=float(pixel.mean()),sbs_pixel_over1_fraction=float(np.mean(np.any(pixel>1,axis=2))))
                        report['product'].append(row)
                        print(json.dumps(row),flush=True)
                        assert row['input_max'] == 0
                        for key in ('normalized_depth_mae','normalized_depth_max','sbs_rgb_mae','sbs_pixel_over1_fraction'):
                            assert row[key]<=report['limits'][key], (key,row)
                        if index==2:
                            cv2.imwrite(str(args.output/f'{source}-{w}x{h}-cpu.png'),cv2.cvtColor(expected,cv2.COLOR_RGB2BGR))
                            cv2.imwrite(str(args.output/f'{source}-{w}x{h}-gpu.png'),cv2.cvtColor(actual,cv2.COLOR_RGB2BGR))
        report['passed'] = True
    finally:
        (args.output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')


if __name__ == '__main__':
    main()
