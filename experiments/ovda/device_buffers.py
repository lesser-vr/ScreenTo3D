# oVDA runtime adaptation, NC-SA-UHDV1.0; see LICENSE and README.md.
"""Fixed inference buffers and same-stream cache/validation operations."""
import ctypes as ct
from depthsbs_app.gpu_runtime import GpuExecution
from .oracle import schedule
from .gpu_input import runtime_library


class OvdaBuffers:
    def __init__(self, engine):
        engine.check()
        self.engine=engine
        self.execution=GpuExecution(engine,engine.stream)
        self.execution.require_current()
        torch=engine.torch
        self.native=runtime_library()
        self.finite=self.native.ovda_check_outputs
        self.finite.argtypes=[ct.c_void_p]*5+[ct.c_size_t]*5+[ct.c_void_p]*2
        self.finite.restype=ct.c_int
        self.shift=self.native.ovda_shift_cache
        self.shift.argtypes=[ct.c_void_p]*2+[ct.c_int]*2+[ct.c_void_p]
        self.shift.restype=ct.c_int
        self.image=torch.empty((1,1,3,*engine.profile),dtype=torch.float32,device=engine.device)
        self.outputs={name:torch.empty(shape,dtype=torch.float32,device=engine.device)
                      for name,(shape,_,is_input) in engine.signature.items() if not is_input}
        self.schedules=tuple(tuple(torch.tensor(v,dtype=torch.int64,device=engine.device)
                                  for v in schedule(used)) for used in range(16))
        self.flag=torch.empty((),dtype=torch.int32,device=engine.device)
        self.host_flag=torch.empty((),dtype=torch.int32,device='cpu',pin_memory=True)
        self.checks=0

    def check_outputs(self):
        engine=self.engine
        self.execution.require_current()
        values=[self.outputs[name] for name in ('depth','new_c1','new_c2','new_c3','new_c4')]
        code=self.finite(*(v.data_ptr() for v in values),*(v.numel() for v in values),
                         self.flag.data_ptr(),int(engine.stream.cuda_stream))
        if code:raise RuntimeError(f'oVDA output validation failed: CUDA {code}')
        self.host_flag.copy_(self.flag,non_blocking=True)
        # One wait owns all TRT outputs and the async 4-byte readback. It must
        # finish before a valid token can be lent or reusable buffers overwritten.
        engine.stream.synchronize()
        self.checks+=1
        if int(self.host_flag):raise ValueError('Nonfinite oVDA output')

    def shift_caches(self):
        engine=self.engine
        self.execution.require_current()
        for key,(n,channels) in engine.caches.items():
            code=self.shift(engine.cache[key].data_ptr(),self.outputs['new_'+key].data_ptr(),
                            n,channels,int(engine.stream.cuda_stream))
            if code:raise RuntimeError(f'oVDA cache update failed: CUDA {code}')

    def bytes(self):
        tensors=(self.image,*self.outputs.values(),*(v for row in self.schedules for v in row),self.flag)
        return sum(v.numel()*v.element_size() for v in tensors)
