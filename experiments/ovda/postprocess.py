# oVDA postprocessing adaptation, NC-SA-UHDV1.0; see LICENSE/README.md.
"""Independent pixel EMA and optional causal depth range on the owner stream."""
import ctypes as ct
import hashlib
import math
import weakref
from screento3d_app.desktop_jobs import ROOT
from screento3d_app.gpu_frame import GpuFrame
from screento3d_app.live_source_gpu_candidate import LiveSourceGpuCandidate
from screento3d_app.live_source_gpu_texture import LiveSourceGpuTexture

DLL_PATH=ROOT/'out/ovda-postprocess-range/ovda_postprocess.dll'
DLL_SHA256='b4873fc3b2b479a825526b1a3fd397e4b255ca1ecc3b3ddbfeec442763372629'
BORROWED_LAYOUT_SHA256='0394a7b790c92db37aaa49190e213edc65914e79625f03d38d62cf3c2911da85'


class OvdaPostBridge:
    def __init__(self,renderer,pixel_alpha,range_parameters=None):
        if not isinstance(pixel_alpha,(float,int)) or isinstance(pixel_alpha,bool) or not math.isfinite(pixel_alpha) or not 0<pixel_alpha<=1:
            raise ValueError('Invalid oVDA pixel EMA weight')
        self.pixel_alpha=float(pixel_alpha)
        self.renderer=weakref.proxy(renderer)
        if renderer.library_sha256!=BORROWED_LAYOUT_SHA256:
            raise RuntimeError('oVDA postprocessing requires the validated borrowed layout')
        if not DLL_PATH.is_file():raise RuntimeError('oVDA postprocessing missing; run scripts/build-ovda-postprocess.ps1')
        if hashlib.sha256(DLL_PATH.read_bytes()).hexdigest()!=DLL_SHA256:
            raise ValueError('oVDA postprocessing DLL checksum mismatch')
        self.post_library=ct.CDLL(str(DLL_PATH))
        self.post_source=self.post_library.ovda_post_source
        self.post_source.argtypes=[ct.c_void_p]*3+[ct.c_int]*2+[ct.c_double]+[ct.c_float]*2+[ct.c_int,ct.c_void_p]+[ct.c_double]*2
        self.post_source.restype=ct.c_int
        self.range_parameters=range_parameters
        if self.range_parameters is None and renderer.policy.stabilize_depth_range:
            from screento3d_app.depth_range import RangeParameters
            self.range_parameters=RangeParameters()
        self.anchors=None;self.range_clock=None;self.range_ready=False
        if self.range_parameters is not None:
            from screento3d_app.depth_range import RangeParameters
            from screento3d_app.stereo_stability import DepthRangeClock
            if not isinstance(self.range_parameters,RangeParameters):raise ValueError('Invalid range parameters')
            self.range_source=self.post_library.ovda_post_source_range
            self.range_source.argtypes=self.post_source.argtypes+[ct.c_void_p]+[ct.c_double]*4
            self.range_source.restype=ct.c_int
            self.range_clock=DepthRangeClock()
            with renderer.engine.torch.cuda.stream(renderer.engine.stream):
                self.anchors=renderer.engine.torch.empty(1024,dtype=renderer.engine.torch.float32,device=renderer.engine.device)

    def post(self,frame,depth,aligned,reset):
        renderer=self.renderer
        renderer._owner()
        gpu=isinstance(frame,GpuFrame)
        if gpu:frame.validate(renderer.engine)
        arguments=(renderer.handle,frame.rgb.data_ptr() if gpu else frame.ctypes.data,
            depth.pointer,2 if gpu else 1,renderer.policy.depth_guide_radius,renderer.policy.temporal_alpha,
            renderer.policy.temporal_color_threshold,renderer.policy.temporal_depth_threshold,int(reset),
            aligned.ctypes.data if aligned is not None else None,renderer.policy.temporal_depth_transition,self.pixel_alpha)
        if self.range_parameters is not None:
            dt,reset=self.range_clock.update(renderer.source_ns,reset=reset or not self.range_ready)
            arguments=(*arguments[:8],int(reset),*arguments[9:])
            p=self.range_parameters
            renderer._check(self.range_source(*arguments,self.anchors.data_ptr(),dt,p.deadband,p.expand_seconds,p.contract_seconds))
            self.range_ready=True
        else:renderer._check(self.post_source(*arguments))
        if not gpu:renderer.h2d+=frame.nbytes

    def close(self):
        # The renderer destroys/fences its borrowed native context first.
        self.anchors=None
        self.range_ready=False


class OvdaPostprocess:
    """Explicit comparison renderer; the product uses the shared source renderer."""
    def __init__(self,*args,pixel_alpha=.18,range_parameters=None,**kwargs):
        super().__init__(*args,**kwargs)
        try:self.bridge=OvdaPostBridge(self,pixel_alpha,range_parameters)
        except BaseException:
            self.close();raise

    def _post(self,frame,depth,aligned,reset):
        self.bridge.post(frame,depth,aligned,reset)

    def close(self):
        super().close()
        bridge=getattr(self,'bridge',None)
        if bridge is not None:bridge.close()


class OvdaGpuCandidate(OvdaPostprocess,LiveSourceGpuCandidate):pass
class OvdaGpuTexture(OvdaPostprocess,LiveSourceGpuTexture):pass
