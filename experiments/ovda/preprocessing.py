# Adapted from Heidelberg University oVDA VideoPreprocessor, NC-SA-UHDV1.0.
# Original authors and full license: README.md and LICENSE in this directory.
# DepthSBS change: one owned uint8 RGB frame only; no source checkout dependency.
import numpy as np
import torch
from depthsbs_app.ovda_geometry import content_rect, validate_dimensions, SUPPORTED_CANVASES


def validate_frame(frame):
    if not isinstance(frame, np.ndarray) or frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError('oVDA preprocessing requires uint8 RGB')
    validate_dimensions(frame.shape[1], frame.shape[0])


class FramePreprocessor:
    def __init__(self, profile=None):
        self.profile = tuple(profile) if profile is not None else None
        if self.profile is not None and self.profile not in SUPPORTED_CANVASES:
            raise ValueError('Unsupported oVDA inference canvas')
        self.mean=torch.tensor([.485,.456,.406],dtype=torch.float32,device='cpu').view(1,1,3,1,1)
        self.std=torch.tensor([.229,.224,.225],dtype=torch.float32,device='cpu').view(1,1,3,1,1)

    def get_size(self,width,height):
        scale=max(518/width,518/height)
        return (max(518,int(np.round(width*scale/14)*14)),
                max(518,int(np.round(height*scale/14)*14)))

    def preprocess(self,frame):
        validate_frame(frame)
        x=torch.from_numpy(frame.transpose(2,0,1)[None,None]).float()
        # Preserve upstream's near-black (max<=1) normalization semantics exactly.
        if x.max()>1.0:x=x/255.0
        h,w=frame.shape[:2]
        if self.profile is None:
            nw,nh=self.get_size(w,h)
            top=left=0
            canvas=(nh,nw)
        else:
            top,left,nh,nw=content_rect(w,h,self.profile)
            canvas=self.profile
        if (h,w)!=(nh,nw):
            x=torch.nn.functional.interpolate(x.flatten(0,1),size=(nh,nw),mode='bicubic',align_corners=False)[None]
        if (nh,nw)!=canvas:
            x=torch.nn.functional.pad(x.flatten(0,1),(left,canvas[1]-nw-left,top,canvas[0]-nh-top),mode='replicate')[None]
        return (x-self.mean)/self.std

    def restore_depth(self, depth, source_shape):
        h,w=source_shape
        if self.profile is not None:
            top,left,rh,rw=content_rect(w,h,self.profile)
            depth=depth[...,top:top+rh,left:left+rw]
        return torch.nn.functional.interpolate(depth,size=(h,w),mode='bilinear',align_corners=True)
