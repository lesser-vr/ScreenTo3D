"""Check each partial sum against sequential double additions on the GPU."""
import ctypes as ct
import json
from pathlib import Path
import numpy as np
import torch

ROOT=Path(__file__).resolve().parents[2]
lib=ct.CDLL(str(ROOT/'out/gpu-load-opt/guide_sum_probe.dll'))
lib.guide_sum_probe.argtypes=[ct.c_void_p]*3+[ct.c_int,ct.c_void_p]
lib.guide_sum_probe.restype=ct.c_int
rng=np.random.default_rng(1106)
stream=torch.cuda.Stream()
cases=[]
for span in (0,1,8,12,13,32,254):
    count=200000
    base=rng.integers(0,256-span,size=(count,1),dtype=np.uint32)
    exp=base+rng.integers(0,span+1,size=(count,9),dtype=np.uint32)
    bits=(rng.integers(0,2,size=(count,9),dtype=np.uint32)<<31)|(exp<<23)|rng.integers(0,1<<23,size=(count,9),dtype=np.uint32)
    # Exercise exact cancellation, signed zero and late fallback, too.
    bits[::3,1]=bits[::3,0]^np.uint32(1<<31)
    bits[::5,2:4]=0
    data=bits.view(np.float32)
    with torch.cuda.stream(stream):
        src=torch.from_numpy(data).cuda()
        actual=torch.empty((count,9),dtype=torch.float64,device='cuda')
        expected=torch.empty_like(actual)
    assert lib.guide_sum_probe(src.data_ptr(),actual.data_ptr(),expected.data_ptr(),count,stream.cuda_stream)==0
    stream.synchronize()
    a,b=actual.cpu().numpy(),expected.cpu().numpy()
    equal=(a==b)|(np.isnan(a)&np.isnan(b))
    assert equal.all(),(span,np.argwhere(~equal)[:10],data[~equal.all(axis=1)][:3],a[~equal.all(axis=1)][:3],b[~equal.all(axis=1)][:3])
    cases.append(dict(exponent_span=span,sequences=count,partial_sums=count*9,exact=True))
(ROOT/'out/gpu-load-opt/sum-parity.json').write_text(json.dumps(dict(completed=True,cases=cases),indent=2))
print('Exact sequential double parity:',sum(c['partial_sums'] for c in cases),'partial sums')
