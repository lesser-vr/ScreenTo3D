"""Causal live depth-range reference; bounded raw anchors, no model dependencies."""
from dataclasses import dataclass
import math
import numpy as np
from .stereo_stability import DepthRangeClock,sample_depth


@dataclass(frozen=True)
class RangeParameters:
    deadband: float = .02
    expand_seconds: float = .05
    contract_seconds: float = .5

    def __post_init__(self):
        values=(self.deadband,self.expand_seconds,self.contract_seconds)
        if (any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in values)
                or not 0 <= self.deadband <= .05 or not 0 < self.expand_seconds <= self.contract_seconds <= 10):
            raise ValueError('Invalid depth-range response parameters')


def settle_bounds(bounds,target,dt,parameters):
    low,high=map(float,bounds);a,b=map(float,target)
    band=parameters.deadband*max(high-low,b-a,1e-6)
    updated=[]
    for endpoint,(old,new) in enumerate(((low,a),(high,b))):
        delta=new-old
        if abs(delta)<=band:updated.append(old);continue
        expanding=delta<0 if endpoint==0 else delta>0
        tau=parameters.expand_seconds if expanding else parameters.contract_seconds
        updated.append(old-math.expm1(-dt/tau)*delta)
    return tuple(updated)


class DepthRangeTracker:
    def __init__(self,parameters=None):
        self.parameters=parameters or RangeParameters()
        self.clock=DepthRangeClock();self.bounds=None;self.anchors=None;self.shape=None

    def update(self,raw,rgb,previous_rgb,target,source_ns=None,*,reset=False):
        if (raw.ndim!=2 or rgb.shape!=(*raw.shape,3) or rgb.dtype!=np.uint8
                or not np.isfinite(raw).all() or not np.isfinite(target).all() or target[1]<target[0]):
            raise ValueError('Invalid depth-range observations')
        dt,reset=self.clock.update(source_ns,reset=reset or raw.shape!=self.shape)
        self.reset_applied=reset
        current=sample_depth(raw).reshape(-1).astype(np.float64)
        bounds=self.bounds
        if reset or bounds is None or self.anchors is None or previous_rgb is None:
            bounds=tuple(map(float,target))
        else:
            if previous_rgb.shape!=rgb.shape or previous_rgb.dtype!=np.uint8:
                raise ValueError('Invalid previous depth-range RGB observation')
            lo,hi=bounds;span=max(hi-lo,1e-6)
            a=(self.anchors-lo)/span;b=(current-lo)/span
            h,w=raw.shape
            y=np.minimum((np.arange(32)*2+1)*h//64,h-1)
            x=np.minimum((np.arange(32)*2+1)*w//64,w-1)
            stationary=np.ones((32,32),bool)
            for dy in (-1,0,1):
                for dx in (-1,0,1):
                    yy=np.clip(y+dy,0,h-1);xx=np.clip(x+dx,0,w-1)
                    diff=rgb[yy[:,None],xx].astype(np.int16)-previous_rgb[yy[:,None],xx].astype(np.int16)
                    stationary &= np.max(np.abs(diff),axis=2)<=4
            valid=stationary.ravel() & (a>.05) & (a<.95) & np.isfinite(b)
            initial=0;accepted=True;gain=1.;offset=0.
            for attempt in range(2):
                if attempt:valid &= np.abs(b-(gain*a+offset))<=.025
                n=int(valid.sum())
                if n<96 or (attempt and n<initial*.8):accepted=False;break
                av,bv=a[valid],b[valid]
                variance=float(np.square(av-av.mean()).sum())
                if variance/n<.005:accepted=False;break
                gain=float(((av-av.mean())*(bv-bv.mean())).sum()/variance)
                offset=float(bv.mean()-gain*av.mean())
                if not .8<=gain<=1.25 or abs(offset)>.15:accepted=False;break
                if attempt and float(np.square(bv-(gain*av+offset)).mean())>.015**2:accepted=False;break
                initial=n
            if accepted:bounds=(lo+offset*span,lo+(offset+gain)*span)
            bounds=settle_bounds(bounds,target,dt,self.parameters)
        self.bounds=bounds;self.anchors=current;self.shape=raw.shape
        return bounds
