"""Allocation arithmetic without CUDA imports, also used before native calls."""
from math import prod
from numbers import Integral

MAX_ALLOCATION=1024**3

def allocation_bytes(shape,itemsize):
    if (not shape or any(isinstance(n,bool) or not isinstance(n,Integral) or n<1 for n in shape)
            or isinstance(itemsize,bool) or not isinstance(itemsize,Integral) or itemsize<1):
        raise ValueError('Invalid CUDA allocation shape/type')
    size=prod(int(n) for n in shape)*int(itemsize)
    if size>MAX_ALLOCATION:raise ValueError('CUDA allocation exceeds limit')
    return size
