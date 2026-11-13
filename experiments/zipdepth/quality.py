"""Matched public sequences through real native SBS; readback is not an FPS test."""
from contextlib import ExitStack
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'v1'))
import cv2
import numpy as np
import torch
from runtime import Engine
from screento3d_app.resources import configure_resource_root
from screento3d_app.desktop_jobs import BUNDLE
from screento3d_app.gpu_frame import GpuFrame
from screento3d_app.small_gpu_input import SmallGpuCaptureEngine
from screento3d_app.live_small_gpu_input import LiveSmallGpuInputTexture
from screento3d_app.live_source_gpu_texture import LiveSourceGpuTexture
from screento3d_app.live_policy import resolve_live
from public_test_media import PublicFrames, SOURCES, ATTRIBUTION

def main():
    out = ROOT/'out/zipdepth-quality-4k-v2'
    out.mkdir(exist_ok=False)
    configure_resource_root(BUNDLE)
    cv2.setNumThreads(1); torch.set_num_threads(4)
    report = dict(completed=False,attribution=ATTRIBUTION,shape=[2160,7680],strength=.25,
        scope='Matched native texture diagnostic; no FPS claim or depth ground truth',
        metrics='Depth residual after RGB optical flow at 480x270, excluding cuts; normalized depth units. Lower residual alone can mean oversmoothing. Edge gradient and depth span are complementary proxies, not truth.',
        rows=[],checks=[])
    def save():
        (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    try:
        with ExitStack() as stack:
            stack.enter_context(os.add_dll_directory('C:/TensorRT/TensorRT-11.2.1.2/bin'))
            engines = {'zipdepth':stack.enter_context(Engine()),'small':stack.enter_context(SmallGpuCaptureEngine(None))}
            renderers = {}
            for name, engine in engines.items():
                cls = LiveSourceGpuTexture if name=='zipdepth' else LiveSmallGpuInputTexture
                model = 'zipdepth-base' if name=='zipdepth' else 'da2-small'
                policy = replace(resolve_live('performance',.25),depth_backend=model)
                renderer = stack.enter_context(cls(3840,2160,policy,engine,diagnostic=True))
                renderer.configure_live_quality('detail')
                renderers[name] = renderer
            xx,yy = np.meshgrid(np.arange(480,dtype=np.float32),np.arange(270,dtype=np.float32))
            flow_engine = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_FAST)
            count = 0
            pixels = np.empty((2160,7680,4),np.uint8)
            for source in SOURCES:
                old, old_gray = {}, None
                frames = PublicFrames(source,120)
                last = None
                for index,rgb in enumerate(frames):
                    if index%2:
                        continue
                    last = rgb
                    gray = cv2.cvtColor(cv2.resize(rgb,(480,270)),cv2.COLOR_RGB2GRAY)
                    flow = None if old_gray is None else flow_engine.calc(gray,old_gray,None)
                    image = cv2.resize(rgb,(3840,2160),interpolation=cv2.INTER_LINEAR)
                    for name,r in renderers.items():
                        if index==0:
                            r.reset()
                        with r.engine.gpu_input.execution.scope():
                            frame = GpuFrame(torch.from_numpy(cv2.cvtColor(image,cv2.COLOR_RGB2BGRA)).cuda(),r.engine)
                        r.source_ns = 1_000_000_000 + round(count*1e9/30)
                        scene = r.inspect_scene(frame)
                        token = r.infer(frame)
                        r.slot = count%2
                        slot,depth = r.render(frame,token,diagnostic=True,scene=scene)
                        # Consume every native slot, including frames without a saved image.
                        r.pool.check(r.pool.dll.live_pool_readback(r.pool.handle,slot,pixels.ctypes.data))
                        assert (pixels[:,:,3]==255).all()
                        d = cv2.resize(depth,(480,270),interpolation=cv2.INTER_AREA)
                        edge = cv2.magnitude(cv2.Sobel(d,cv2.CV_32F,1,0),cv2.Sobel(d,cv2.CV_32F,0,1))
                        row = dict(source=source,index=index,model=name,cut=bool(scene.cut),
                                   depth_span=float(np.percentile(d,95)-np.percentile(d,5)),gradient_mean=float(edge.mean()))
                        if flow is not None and not scene.cut:
                            mx,my = xx+flow[:,:,0], yy+flow[:,:,1]
                            valid = (mx>=0)&(mx<479)&(my>=0)&(my<269)
                            warped = cv2.remap(old[name],mx,my,cv2.INTER_LINEAR)
                            old_rgb = cv2.remap(old_gray,mx,my,cv2.INTER_LINEAR)
                            valid &= np.abs(gray.astype(float)-old_rgb)<20
                            moving = valid & (np.linalg.norm(flow,axis=2)>.5)
                            residual = np.abs(d-warped)
                            row.update(residual=float(residual[valid].mean()) if valid.any() else None,
                                       moving_residual=float(residual[moving].mean()) if moving.any() else None,
                                       valid_fraction=float(valid.mean()))
                        if index in (0,58,118):
                            cv2.imwrite(str(out/f'{source}-{index}-{name}-sbs.png'),cv2.cvtColor(pixels[:,:,:3],cv2.COLOR_RGB2BGR))
                            cv2.imwrite(str(out/f'{source}-{index}-{name}-depth.png'),(np.clip(depth,0,1)*255).astype(np.uint8))
                        old[name] = d
                        report['rows'].append(row)
                    old_gray = gray
                    count += 1
                # A repeated frame detects drift; reset then replay checks history clearing.
                image = cv2.resize(last,(3840,2160),interpolation=cv2.INTER_LINEAR)
                for name,r in renderers.items():
                    prior = None
                    differences=[]
                    for j in range(12):
                        with r.engine.gpu_input.execution.scope():
                            frame = GpuFrame(torch.from_numpy(cv2.cvtColor(image,cv2.COLOR_RGB2BGRA)).cuda(),r.engine)
                        r.source_ns += 33_333_333
                        r.slot = j%2
                        slot,depth = r.render(frame,r.infer(frame),diagnostic=True)
                        r.pool.check(r.pool.dll.live_pool_readback(r.pool.handle,slot,pixels.ctypes.data))
                        if prior is not None:
                            differences.append(float(np.abs(depth-prior).mean()))
                        prior = depth
                    report['checks'].append(dict(source=source,model=name,static_last_delta=differences[-1],static_max_delta=max(differences)))
                save()
                print(source, 'completed',flush=True)
            report['engines'] = {name:e.telemetry() for name,e in engines.items()}
        report['completed'] = True
    except BaseException as exc:
        report['error'] = repr(exc); raise
    finally:
        save()

if __name__ == '__main__':
    main()
