# Adapted from Heidelberg University oVDA VideoPreprocessor, NC-SA-UHDV1.0.
# Original authors and full license: README.md and LICENSE in this directory.
# DepthSBS change: one owned uint8 RGB frame only; no source checkout dependency.
import numpy as np
import torch


class FramePreprocessor:
    def __init__(self):
        self.mean=torch.tensor([.485,.456,.406],dtype=torch.float32,device='cpu').view(1,1,3,1,1)
        self.std=torch.tensor([.229,.224,.225],dtype=torch.float32,device='cpu').view(1,1,3,1,1)

    def get_size(self,width,height):
        scale=max(518/width,518/height)
        return (max(518,int(np.round(width*scale/14)*14)),
                max(518,int(np.round(height*scale/14)*14)))

    def preprocess(self,frame):
        if not isinstance(frame,np.ndarray) or frame.dtype!=np.uint8 or frame.ndim!=3 or frame.shape[2]!=3:
            raise ValueError('oVDA preprocessing requires uint8 RGB')
        x=torch.from_numpy(frame.transpose(2,0,1)[None,None]).float()
        # Preserve upstream's near-black (max<=1) normalization semantics exactly.
        if x.max()>1.0:x=x/255.0
        h,w=frame.shape[:2];nw,nh=self.get_size(w,h)
        if (h,w)!=(nh,nw):
            x=torch.nn.functional.interpolate(x.flatten(0,1),size=(nh,nw),mode='bicubic',align_corners=False)[None]
        return (x-self.mean)/self.std
