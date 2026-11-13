"""Bounded Base CUDA stage probe; diagnostic readback is outside measured work."""
import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import statistics
import time

import cv2
import numpy as np
from screento3d_app.da2_base import binding
from screento3d_app.desktop_jobs import ROOT, BUNDLE
from screento3d_app.resources import configure_resource_root
from screento3d_app.gpu_frame import GpuFrame
from screento3d_app.live_source_gpu_texture import LiveSourceGpuTexture
from screento3d_app.live_policy import resolve_live
from public_test_media import CORPUS


from screento3d_app.environment import get as app_env

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    os.environ['SCREENTO3D_BASE_STAGE_PROFILE'] = '1'
    configure_resource_root(BUNDLE)
    video = cv2.VideoCapture(str(CORPUS/'FloorballGame.mp4'))
    ok, bgr = video.read()
    video.release()
    assert ok
    rows = []
    for width, height in ((1920,1080),(3840,2160)):
        with ExitStack() as stack:
            runtime = Path('C:/TensorRT/TensorRT-11.2.1.2/bin')
            stack.enter_context(os.add_dll_directory(str(runtime)))
            backend = binding(ROOT/'out/da2-base-local', runtime, device_depth=True)
            backend.input_validator(dict(width=width,height=height))
            engine = stack.enter_context(backend.engine_factory(None))
            projection = stack.enter_context(LiveSourceGpuTexture(width,height,resolve_live('balanced'),engine,diagnostic=True))
            bgra = cv2.cvtColor(cv2.resize(bgr,(width,height)),cv2.COLOR_BGR2BGRA)
            with engine.torch.cuda.stream(engine.stream):
                tensor = engine.torch.from_numpy(bgra).cuda()
            engine.stream.synchronize()
            pixels = np.empty((height,width*2,4), np.uint8)
            samples = []
            for i in range(36):
                started = time.perf_counter()
                frame = GpuFrame(tensor,engine)
                depth = projection.infer(frame)
                inferred = time.perf_counter()
                projection.slot = i%2
                slot = projection.render(frame,depth)
                elapsed = time.perf_counter()-started
                if i>=6:
                    samples.append(dict(engine.last_stage_ms,
                        infer_host_ms=(inferred-started)*1000,
                        total_ms=elapsed*1000,
                        stereo_host_ms=(time.perf_counter()-inferred)*1000,
                        projection_ms=projection.projection_ms.tolist()))
                projection.pool.check(projection.pool.dll.live_pool_readback(projection.pool.handle,slot,pixels.ctypes.data))
            row = dict(size=[width,height],samples=samples,median_ms={k:statistics.median(s[k] for s in samples)
                for k in samples[0] if k!='projection_ms'},
                projection_median_ms=np.median([s['projection_ms'] for s in samples],axis=0).tolist())
            rows.append(row)
            print(json.dumps({k:v for k,v in row.items() if k!='samples'}),flush=True)
    (args.output/'report.json').write_text(json.dumps(dict(
        scope='Isolated CUDA stage probe; not capture/display FPS',
        cuda_graph=app_env('SCREENTO3D_BASE_GRAPH', '0'), rows=rows),indent=2))


if __name__ == '__main__':
    main()
