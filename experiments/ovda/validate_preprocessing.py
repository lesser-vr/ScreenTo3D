# NC-SA-UHDV1.0; exact original-preprocessor parity, not a new model recipe.
import json
import uuid
import numpy as np
import torch
from oracle import ROOT, upstream
from preprocessing import FramePreprocessor


def main():
    _,cls=upstream()
    reference=cls(input_size=518,device='cpu',ensure_multiple_of=14,keep_aspect_ratio=True,resize_method='lower_bound')
    candidate=FramePreprocessor()
    rng=np.random.default_rng(20260905)
    rows=[]
    for h,w in ((608,1056),(720,1280),(1080,1920),(2160,3840),(720,960),(518,686)):
        for pattern in ('zero','one','random'):
            frame=(np.full((h,w,3),int(pattern=='one'),np.uint8) if pattern!='random'
                   else rng.integers(0,256,(h,w,3),dtype=np.uint8))
            frame.setflags(write=False)
            a=reference.preprocess(frame.copy()).numpy()
            b=candidate.preprocess(frame.copy()).numpy()
            np.testing.assert_array_equal(a,b)
            rows.append(dict(width=w,height=h,pattern=pattern,shape=list(b.shape),max_abs=0.0))
    for width in range(650,1425,7):
        assert reference.get_size(width,720)==candidate.get_size(width,720)
    previous=torch.get_default_dtype()
    try:
        torch.set_default_dtype(torch.float64)
        assert FramePreprocessor().preprocess(np.ones((608,1056,3),np.uint8)).dtype==torch.float32
    finally:torch.set_default_dtype(previous)
    root=ROOT/'out/ovda-preprocessing'/uuid.uuid4().hex;root.mkdir(parents=True)
    (root/'report.json').write_text(json.dumps(dict(passed=True,comparisons=rows,size_sweep=True),indent=2))
    print(root/'report.json',flush=True)


if __name__=='__main__':main()
