"""A same-stream owned RGB frame with bounded CPU scene/border observations."""
import numpy as np


class GpuFrame:
    dtype = np.dtype('uint8')
    ndim = 3

    def __init__(self, bgra, engine):
        engine._check()
        self.execution = engine.gpu_input.execution
        self.execution.validate_image(bgra, channels=(4,))
        self.engine = engine
        self.readback_bytes = 0
        self.readback_syncs = 0
        self._thumbnail = self._border = self._host = None
        with self.execution.scope():
            if self.execution.native:
                memory=engine.memory
                self.rgb=memory.empty((*bgra.shape[:2],3),np.uint8)
                memory.result(memory.dll.memory_color(bgra.data_ptr(),self.rgb.data_ptr(),bgra.shape[1],bgra.shape[0],self.execution.handle))
            else:self.rgb = bgra[:, :, :3].flip(-1).contiguous()
        self.shape = tuple(self.rgb.shape)
        self.nbytes = self.rgb.numel()

    def validate(self, engine):
        self.execution.check()
        if self.engine is not engine or not self.rgb.is_contiguous():
            raise ValueError('GPU frame belongs to another engine/stream')

    def thumbnail(self):
        self.validate(self.engine)
        if self._thumbnail is None:
            self._thumbnail = self.engine.gpu_input.thumbnail(self.rgb)
            self.readback_bytes += self._thumbnail.nbytes
            self.readback_syncs += 1
        return self._thumbnail

    def border(self):
        self.validate(self.engine)
        if self._border is None:
            if self.execution.native:
                from .cuda_memory import cudart,_cuda
                h,w,_=self.shape;result=np.empty((2*w+2*h,3),np.uint8);p=result.ctypes.data;src=self.rgb.data_ptr()
                kind=cudart.cudaMemcpyKind.cudaMemcpyDeviceToHost;stream=self.execution.handle
                _cuda(cudart.cudaMemcpyAsync(p,src,w*3,kind,stream))
                _cuda(cudart.cudaMemcpyAsync(p+w*3,src+(h-1)*w*3,w*3,kind,stream))
                _cuda(cudart.cudaMemcpy2DAsync(p+2*w*3,3,src,w*3,3,h,kind,stream))
                _cuda(cudart.cudaMemcpy2DAsync(p+(2*w+h)*3,3,src+(w-1)*3,w*3,3,h,kind,stream))
                self.execution.stream.synchronize();self._border=result
                self.readback_bytes+=result.nbytes;self.readback_syncs+=1
                return result
            torch = self.execution.torch
            with self.execution.scope():
                self._border = torch.cat((self.rgb[0], self.rgb[-1], self.rgb[:, 0], self.rgb[:, -1])).cpu().numpy()
            self.readback_bytes += self._border.nbytes
            self.readback_syncs += 1
        return self._border

    def to_host(self):
        self.validate(self.engine)
        if self._host is None:
            with self.execution.scope():
                self._host = self.rgb.download() if self.execution.native else self.rgb.cpu().numpy()
            self.readback_bytes += self._host.nbytes
            self.readback_syncs += 1
        return self._host

    def same_pixels(self, other):
        if not isinstance(other, GpuFrame) or self.shape != other.shape:
            return False
        self.validate(other.engine)
        with self.execution.scope():
            result = (self.engine.memory.equal(self.rgb,other.rgb) if self.execution.native else
                      bool(self.execution.torch.equal(self.rgb, other.rgb)))
        self.readback_bytes += 4 if self.execution.native else 1
        self.readback_syncs += 1
        return result
