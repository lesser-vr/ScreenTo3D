"""GPU Small input with unchanged Small postprocessing/native output layout."""
import ctypes as ct

from .gpu_frame import GpuFrame
from .live_gpu_candidate import LiveGpuCandidate
from .live_gpu_texture import TextureOutputMixin
from .small_gpu_input import DLL_PATH, DLL_SHA256, cubic_coefficients


class LiveSmallGpuInput(LiveGpuCandidate):
    library_path = DLL_PATH
    library_sha256 = DLL_SHA256

    def __init__(self, *args, **kwargs):
        self.coefficients = self.input_frame = None
        super().__init__(*args, **kwargs)
        self.dll.small_prepare.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_size_t,
                                          ct.c_int, ct.c_int, ct.c_void_p, ct.c_void_p]
        self.dll.live_post_gpu.argtypes = self.dll.live_post.argtypes
        try:
            gpu = self.engine.gpu_input.execution
            with gpu.scope():
                coefficients=cubic_coefficients(self.width,self.height)
                self.coefficients=(self.engine.memory.from_numpy(coefficients) if gpu.native else
                                   gpu.torch.from_numpy(coefficients).to(gpu.device))
        except BaseException as primary:
            try:
                self.close()
            except Exception as cleanup:
                primary.add_note(f'Small GPU input cleanup failed: {cleanup!r}')
            raise

    def infer(self, frame):
        self._owner()
        if not isinstance(frame, GpuFrame) or frame.shape != (self.height, self.width, 3):
            raise ValueError('Small GPU inference requires an owned GPU frame')
        frame.validate(self.engine)
        self.small_rgb = True  # Enables the inherited live_times telemetry.

        def prepare(pointer, stream):
            if stream != self._stream(self.engine):
                raise ValueError('Unexpected Small input stream')
            # infer_prepared_device has drained any previous submission first.
            self.input_frame = frame
            self._check(self.dll.small_prepare(self.handle, frame.rgb.data_ptr(),
                frame.rgb.stride(0), self.width, self.height, pointer, self.coefficients.data_ptr()))

        return self.engine.infer_prepared_device(prepare)

    def _post(self, frame, depth, aligned, reset):
        frame.validate(self.engine)
        self._check(self.dll.live_post_gpu(self.handle, frame.rgb.data_ptr(), depth.pointer,
            self.policy.depth_guide_radius, self.policy.temporal_alpha,
            self.policy.temporal_color_threshold, self.policy.temporal_depth_threshold,
            int(reset), aligned.ctypes.data if aligned is not None else None,
            self.policy.temporal_depth_transition))

    def close(self):
        # live_destroy drains the owned stream before releasing borrowed tensors.
        super().close()
        self.coefficients = self.input_frame = None


class LiveSmallGpuInputTexture(TextureOutputMixin, LiveSmallGpuInput):
    borrowed_layout_sha256 = DLL_SHA256
