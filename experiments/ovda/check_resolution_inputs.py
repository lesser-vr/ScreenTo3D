# oVDA input diagnostics, NC-SA-UHDV1.0; see LICENSE/README.md.
"""Exact prior-canvas CUDA control and trial padding restoration."""
import argparse
import ctypes as ct
import hashlib
import json
from pathlib import Path
import numpy as np
import torch
from depthsbs_app import ovda
from depthsbs_app.desktop_jobs import ROOT
from depthsbs_app.ovda_geometry import CANVASES,content_rect


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    ovda.runtime_class(True)
    from _depthsbs_ovda.preprocessing import FramePreprocessor
    from check_gpu_input import InputOwner
    old_path=ROOT/'out/ovda-gpu-input/ovda_input.dll'
    assert hashlib.sha256(old_path.read_bytes()).hexdigest()=='89c5caea88cf1f074855fa0a97d833626f3b6666b11405313b8005a8d4b8375e'
    library=ct.CDLL(str(old_path));old=library.ovda_prepare
    owner=InputOwner();old.argtypes=owner.gpu_input.launch.argtypes;old.restype=ct.c_int
    report=dict(native_exact=0,restoration=[],old_dll_sha256=hashlib.sha256(old_path.read_bytes()).hexdigest())
    try:
        rng=np.random.default_rng(931)
        for shape in CANVASES:
            for channels in (3,4):
                for pattern in ('zero','one','binary','random','pitched'):
                    values=(np.full((144,256,channels),int(pattern=='one'),np.uint8) if pattern in ('zero','one') else
                            rng.integers(0,2 if pattern=='binary' else 256,(144,256,channels),dtype=np.uint8))
                    with torch.cuda.stream(owner.stream):
                        rgb=torch.from_numpy(values).to(owner.device)
                        if pattern=='pitched':
                            backing=torch.empty((144,263,channels),dtype=torch.uint8,device=owner.device)
                            view=backing[:,:256];view.copy_(rgb);rgb=view
                        actual=owner.gpu_input.prepare(rgb,shape)
                        expected=torch.empty_like(actual)
                        code=old(rgb.data_ptr(),rgb.stride(0),256,144,channels,*shape,*content_rect(256,144,shape),
                                 expected.data_ptr(),owner.gpu_input.flag.data_ptr(),int(owner.stream.cuda_stream))
                        assert code==0 and torch.equal(expected,actual)
                    report['native_exact']+=1
        shape=(392,700);pre=FramePreprocessor(shape)
        for w,h in ((1280,720),(3840,2160),(3440,1440),(1080,1920),(1024,1024),(16,2160)):
            top,left,rh,rw=content_rect(w,h,shape)
            depth=torch.full((1,1,*shape),-1000.)
            depth[...,top:top+rh,left:left+rw]=torch.linspace(1,2,rw).view(1,1,1,rw)
            result=pre.restore_depth(depth,(h,w))
            assert result.shape==(1,1,h,w) and float(result.min())>=1 and float(result.max())<=2
            report['restoration'].append(dict(size=[w,h],rect=[top,left,rh,rw]))
        report['passed']=True
    finally:
        owner.stream.synchronize();owner.closed=True
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2))
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
