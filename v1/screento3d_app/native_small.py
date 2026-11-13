"""Small uses its original TensorRT engine with CUDA-owned frame buffers."""
from .trt_backend import DepthEngine,_cuda,cudart
from .cuda_memory import Stream,Arena
from .gpu_runtime import GpuInputSupport
from .small_gpu_input import DLL_PATH,DLL_SHA256

class NativeSmallEngine(DepthEngine):
    native=True
    def __init__(self,progress=None):
        self.memory=self.execution_stream=self.gpu_input=None
        super().__init__(progress)
        try:
            self.device=int(_cuda(cudart.cudaGetDevice()))
            self.execution_stream=Stream(self.device,handle=int(self.stream))
            self.memory=Arena(self.execution_stream,self._check)
            self.gpu_input=GpuInputSupport(self,DLL_PATH,DLL_SHA256,stream=self.execution_stream)
        except BaseException:
            self.close();raise
    def _check(self):
        self._device_check()
        if int(_cuda(cudart.cudaGetDevice()))!=self.device:raise RuntimeError('Small CUDA device changed')
    def close(self):
        errors=[]
        if self.memory is not None:
            try:self.memory.close()
            except Exception as exc:errors.append(exc)
            self.memory=None
        try:super().close()
        except Exception as exc:errors.append(exc)
        if self.execution_stream is not None:self.execution_stream.closed=True
        self.gpu_input=None
        if errors:raise ExceptionGroup('Small CUDA cleanup failed',errors)
