"""Bounded 2x file cadence preserving original timestamps and total duration."""
import numpy as np


class DoubleRate:
    def __init__(self,generate):
        self.generate=generate;self.previous=None
        self.closed=False
        self.originals=self.generated=self.cut_repeats=self.tail_repeats=0

    def submit(self,current,*,cut_before=False):
        if self.closed:raise RuntimeError('File interpolation already finished')
        if current.dtype!=np.uint8 or current.ndim!=3 or current.shape[2]!=3:
            raise ValueError('File interpolation requires uint8 RGB stereo frames')
        if self.previous is None:result=(current,)
        else:
            if current.shape!=self.previous.shape:raise ValueError('File interpolation geometry changed')
            if cut_before:middle=self.previous;self.cut_repeats+=1
            else:
                middle=self.generate(self.previous,current)
                if middle.shape!=current.shape or middle.dtype!=np.uint8:
                    raise ValueError('Invalid file interpolation result')
                self.generated+=1
            result=(middle,current)
        self.previous=current.copy();self.originals+=1
        return result

    def finish(self):
        self.closed=True
        if self.previous is None:return ()
        tail=self.previous;self.previous=None;self.tail_repeats+=1
        return (tail,)

    def telemetry(self):
        return dict(enabled=True,multiplier=2,original_frames=self.originals,
                    generated_frames=self.generated,cut_repeats=self.cut_repeats,tail_repeats=self.tail_repeats)
