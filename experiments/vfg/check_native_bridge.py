"""Exact original-frame parity and mixed TRT11/VFG SDK runtime smoke."""
import argparse
from contextlib import ExitStack
from dataclasses import replace
import ctypes as ct
import json
import os
from pathlib import Path
import cv2
import numpy as np
import torch
from screento3d_app.da2_base import binding
from screento3d_app.desktop_jobs import ROOT, BUNDLE
from screento3d_app.resources import configure_resource_root
from screento3d_app.live_policy import resolve_live
from screento3d_app.gpu_frame import GpuFrame
from screento3d_app.live_source_gpu_texture import LiveSourceGpuTexture
from screento3d_app.live_small_gpu_input import LiveSmallGpuInputTexture
from screento3d_app.small_gpu_input import SmallGpuCaptureEngine
from public_test_media import PublicFrames
from native_path import vfg_renderer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--quality", choices=("reference", "anchor", "subpixel", "stable", "coverage", "range", "motion", "window", "budget", "detail"), default="reference")
    parser.add_argument('--model',choices=('da2-base','da2-small'),default='da2-base')
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    configure_resource_root(BUNDLE)
    cv2.setNumThreads(1)
    torch.set_num_threads(4)
    policy = replace(resolve_live("performance" if args.model=='da2-small' else "balanced",strength=.25),
                     depth_backend=args.model)
    rows = []
    generated_windows = []
    for width, height in ((1920,1080), (3840,2160)):
        with ExitStack() as stack:
            runtime = Path("C:/TensorRT/TensorRT-11.2.1.2/bin")
            stack.enter_context(os.add_dll_directory(str(runtime)))
            if args.model=='da2-small':
                engine=stack.enter_context(SmallGpuCaptureEngine())
                old_type,new_type=LiveSmallGpuInputTexture,vfg_renderer(args.model)
                stream=engine.torch_stream
            else:
                backend = binding(ROOT / "out/da2-base-local", runtime, device_depth=True)
                backend.input_validator(dict(width=width, height=height))
                engine = stack.enter_context(backend.engine_factory(None))
                old_type,new_type=LiveSourceGpuTexture,vfg_renderer(args.model)
                stream=engine.stream
            old = stack.enter_context(old_type(width,height,policy,engine,diagnostic=True))
            new = stack.enter_context(new_type(width,height,policy,engine,diagnostic=True))
            old.configure_live_quality(args.quality)
            new.configure_live_quality(args.quality)
            references = []
            windows = []
            window_buffers = []
            for i, rgb in enumerate(PublicFrames("FloorballGame",3)):
                rgb = cv2.resize(rgb,(width,height))
                with torch.cuda.stream(stream):
                    frame = GpuFrame(torch.from_numpy(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGRA)).cuda(),engine)
                old.slot = i % 2
                old.source_ns = new.source_ns = 1_000_000_000 + i * 16_666_667
                slot = old.render(frame,old.infer(frame))
                expected = np.empty((height,width*2,4),np.uint8)
                old.pool.check(old.pool.dll.live_pool_readback(old.pool.handle,slot,expected.ctypes.data))
                new.render(frame,new.infer(frame))
                if args.quality in ('window','budget','detail'):
                    old.dll.live_window_snapshot.argtypes = [ct.c_void_p,ct.c_void_p]
                    values=np.empty(4,np.float32)
                    assert old.dll.live_window_snapshot(old.handle,values.ctypes.data)==0
                    windows.append(values[2:].copy())
                with torch.cuda.stream(stream):
                    actual = new.current.cpu().numpy()
                    references.append(new.current.clone())
                    window_buffers.append(new.current_window.clone())
                assert np.array_equal(actual,expected), "Original SBS changed"
                new.publish_pixels(new.current,0)
                delivered = np.empty_like(expected)
                new.pool.check(new.pool.dll.live_pool_readback(new.pool.handle,0,delivered.ctypes.data))
                assert np.array_equal(delivered,expected), "Native RGBA publication changed"
                rows.append(dict(width=width,height=height,index=i,original_exact=True,native_exact=True))
            new.generate(references[0],references[2],new.middle,window_buffers[0],window_buffers[2])
            with torch.cuda.stream(stream):
                generated = new.middle.cpu().numpy()
            assert generated.shape == expected.shape
            if windows:
                common=np.floor(np.maximum(windows[0],windows[2])).astype(int)
                left=int(generated[:,:common[0],:3].max(initial=0))
                right=int(generated[:,width*2-common[1]:,:3].max(initial=0))
                generated_windows.append(dict(size=[width,height],protected_black_columns=common.tolist(),
                                              max_rgb=[left,right]))
                assert max(left,right)<=1,generated_windows[-1]
            assert cv2.imwrite(str(args.output/f"{width}x{height}-generated.png"),cv2.cvtColor(generated,cv2.COLOR_RGBA2BGRA))
            references.clear()
            window_buffers.clear()
    (args.output / "result.json").write_text(json.dumps(dict(passed=True,model=args.model,quality=args.quality,
                                                          rows=rows,generated_windows=generated_windows),indent=2))
    print("6 original/native exact parity cases and two VFG sizes passed")


if __name__ == "__main__":
    main()
