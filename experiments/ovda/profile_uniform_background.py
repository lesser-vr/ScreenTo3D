# oVDA diagnostic, NC-SA-UHDV1.0; see LICENSE/README.md.
"""Explicit isolated CPU profile on the supplied flower scene, not live FPS."""
import argparse
import cProfile
from dataclasses import replace
import io
import json
from pathlib import Path
import pstats
import cv2
import numpy as np
import torch
from screento3d_app import ovda
from screento3d_app.desktop_jobs import ROOT,BUNDLE
from screento3d_app.resources import configure_resource_root
from screento3d_app.live_model import model_adapter
from screento3d_app.live_policy import resolve_live
from screento3d_app.live_source_gpu_texture import LiveSourceGpuTexture
from screento3d_app.gpu_frame import GpuFrame
from screento3d_app.stereo import refine_flat_background


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--input',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    configure_resource_root(BUNDLE)
    cap=cv2.VideoCapture(str(args.input));ok,bgr=cap.read();cap.release();assert ok
    policy=model_adapter('ovda-small-c16').apply_live_policy(replace(resolve_live('video-quality',.5),depth_backend='ovda-small-c16',stereo_layout='half-tb'))
    cls=ovda.runtime_class(True);rows=[]
    for w,h in ((1920,1080),(3840,2160)):
        engine=cls();post=None;profiler=cProfile.Profile()
        try:
            rgb=np.ascontiguousarray(cv2.cvtColor(cv2.resize(bgr,(w,h)),cv2.COLOR_BGR2RGB))
            border=np.concatenate((rgb[0],rgb[-1],rgb[:,0],rgb[:,-1]))
            color=np.median(border,axis=0).astype(np.float32)
            uniform=float(np.mean(np.max(np.abs(border.astype(np.float32)-color),axis=1)<=.04*255))
            from screento3d_app.stereo import uniform_color_mask
            coverage=float(uniform_color_mask(rgb,color,.04).mean())
            post=LiveSourceGpuTexture(w,h,replace(policy,flat_background_refinement=False),engine,diagnostic=True)
            snapshots=[];refinements=0
            for i in range(3):
                with torch.cuda.stream(engine.stream):frame=GpuFrame(torch.from_numpy(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGRA)).to(engine.device),engine)
                token=post.infer(frame);post.source_ns=1_000_000_000+i*16_666_667;post.slot=i%2
                slot,aligned=post.render(frame,token,diagnostic=True)
                rgba=np.empty((h,w,4),np.uint8)
                post.pool.check(post.pool.dll.live_pool_readback(post.pool.handle,slot,rgba.ctypes.data))
                refined=profiler.runcall(refine_flat_background,rgb,aligned,tolerance=policy.flat_background_tolerance,
                            minimum_coverage=policy.flat_background_min_coverage,radius=policy.depth_guide_radius)
                refinements+=int(refined is not aligned)
                snapshots.append(dict(post.last))
            stream=io.StringIO();pstats.Stats(profiler,stream=stream).strip_dirs().sort_stats('tottime').print_stats(18)
            (args.output/f'{w}x{h}-cpu.txt').write_text(stream.getvalue())
            profiler.dump_stats(str(args.output/f'{w}x{h}.pstats'))
            rows.append(dict(size=[w,h],border_uniform_fraction=uniform,matching_color_fraction=coverage,
                             cpu_refinements=refinements,postprocessing=snapshots))
            print(stream.getvalue(),flush=True)
        finally:
            if post is not None:post.close()
            engine.close()
    (args.output/'report.json').write_text(json.dumps(dict(rows=rows,scope='isolated three-frame legacy CPU reference profile on prepared depth; not product policy or WGC output FPS'),indent=2))


if __name__=='__main__':main()
