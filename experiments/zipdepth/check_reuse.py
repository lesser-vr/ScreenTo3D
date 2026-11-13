"""Exercise exact-RGB reuse through the real ZipDepth native renderer."""
from dataclasses import replace
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'v1'))

def main():
    import argparse
    import cv2
    import numpy as np
    import torch
    from runtime import Engine
    from screento3d_app.resources import configure_resource_root
    from screento3d_app.desktop_jobs import BUNDLE
    from screento3d_app.gpu_frame import GpuFrame
    from screento3d_app.live_source_gpu_texture import LiveSourceGpuTexture
    from screento3d_app.live_policy import resolve_live,refresh_live
    from public_test_media import PublicFrames
    p=argparse.ArgumentParser();p.add_argument('--tag',required=True);args=p.parse_args()
    out=ROOT/f'out/zipdepth-reuse-{args.tag}.json'
    if out.exists():raise FileExistsError(out)
    report=dict(completed=False,cases=[])
    configure_resource_root(BUNDLE)
    image=PublicFrames('OfficeWalk',1)[0]
    policy=replace(resolve_live('performance',.25),depth_backend='zipdepth-base')
    try:
        with Engine() as engine:
            old=None
            for width,height in ((960,540),(960,960),(3840,2160)):
                pixels=np.empty((height,width*2,4),np.uint8)
                rgb=cv2.resize(image,(width,height))
                inferred=None;token=None;reused=0;inferred_count=0
                with LiveSourceGpuTexture(width,height,policy,engine,diagnostic=True) as renderer:
                    renderer.configure_live_quality('detail')
                    for index in range(12):
                        # Change the whole frame midway; never reuse after changed RGB.
                        source=rgb if index<6 else 255-rgb
                        with engine.gpu_input.execution.scope():
                            frame=GpuFrame(torch.from_numpy(cv2.cvtColor(source,cv2.COLOR_RGB2BGRA)).cuda(),engine)
                        refresh=refresh_live(frame,inferred,index,policy,False)
                        if refresh!='reuse':
                            prior=token if token is not None else old
                            token=renderer.infer(frame);inferred=frame;inferred_count+=1
                            if prior is not None:
                                try:prior.validate()
                                except ValueError:pass
                                else:raise AssertionError('Superseded token remained valid')
                        else:reused+=1
                        renderer.source_ns=1_000_000_000+index*16_666_667
                        renderer.slot=index%2
                        slot=renderer.render(frame,token)
                        renderer.pool.check(renderer.pool.dll.live_pool_readback(renderer.pool.handle,slot,pixels.ctypes.data))
                        assert np.all(pixels[:,:,3]==255)
                    assert reused>0 and inferred_count>1
                    old=token
                report['cases'].append(dict(width=width,height=height,frames=12,reused=reused,inferences=inferred_count))
            token.validate()
        try:token.validate()
        except RuntimeError:pass
        else:raise AssertionError('Closed engine result remained valid')
        report['completed']=True
    except BaseException as exc:
        report['error']=repr(exc);raise
    finally:out.write_text(json.dumps(report,indent=2),encoding='utf-8')

if __name__=='__main__':main()
