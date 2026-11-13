# oVDA validation, NC-SA-UHDV1.0; see LICENSE/README.md.
"""CPU contracts for unchanged native transforms and padded-depth restoration."""
import argparse
import json
from pathlib import Path
import numpy as np
import torch
from preprocessing import FramePreprocessor, validate_frame
from screento3d_app.ovda_geometry import content_rect, select_profile


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    rows=[]
    rng=np.random.default_rng(911)
    for width,height in ((1056,608),(1280,720),(1920,1080),(3840,2160),(960,720)):
        profile=select_profile(width,height)
        for pattern in ('zero','one','random'):
            frame=(rng.integers(0,256,(height,width,3),dtype=np.uint8) if pattern=='random'
                   else np.full((height,width,3),int(pattern=='one'),np.uint8))
            original=FramePreprocessor().preprocess(frame)
            adapted=FramePreprocessor(profile).preprocess(frame)
            assert torch.equal(original,adapted), (width,height,pattern)
        rows.append(dict(size=[width,height],canvas=profile,native_exact=True))
    for width,height in ((3440,1440),(3840,1600),(1080,1920),(1024,1024),(4096,512),(16,2160)):
        profile=select_profile(width,height)
        pre=FramePreprocessor(profile)
        frame=np.full((height,width,3),123,np.uint8)
        frame.setflags(write=False)
        validate_frame(frame)
        image=pre.preprocess(frame.copy())
        assert image.shape==(1,1,3,*profile)
        assert torch.isfinite(image).all()
        top,left,h,w=content_rect(width,height,profile)
        assert 0<=top and 0<=left and top+h<=profile[0] and left+w<=profile[1]
        assert abs(w/width-h/height)<=max(1/width,1/height)
        # A sentinel in the padding must not contaminate any restored depth.
        depth=torch.full((1,1,*profile),-1000.)
        depth[...,top:top+h,left:left+w]=torch.linspace(1,2,w).view(1,1,1,w).expand(1,1,h,w)
        restored=pre.restore_depth(depth,(height,width))
        assert restored.shape==(1,1,height,width)
        assert float(restored.min())>=1 and float(restored.max())<=2
        rows.append(dict(size=[width,height],canvas=profile,rect=[top,left,h,w],restoration=True))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(dict(passed=True,cases=rows),indent=2))
    print('PASS native parity and aspect-fit:',len(rows),'geometries',flush=True)


if __name__=='__main__':main()
