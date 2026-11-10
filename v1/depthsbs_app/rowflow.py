"""Explicit Base-only learned-renderer experiment; normal runtime never imports it."""
import ctypes as ct
from functools import lru_cache
import hashlib
import importlib.util
import os
import subprocess
import sys

from .desktop_jobs import ROOT
from .live_gpu_candidate import DLL_SHA256
from .live_source_gpu_candidate import LiveSourceGpuCandidate
from .live_texture_pool import LiveTexturePool

SOURCE = ROOT/'out/iw3-render-source-20261105'
REVISION = '0d3d92c8f4396da564c44524b6390ee5c76b9668'
WEIGHT = ROOT/'out/iw3-render-models-20261105/iw3_row_flow_v3_sym_20250628.pth'
WEIGHT_HASH = 'b61518f9c83e1f0c19d8a8844dbe5304e5f47bfb65928d5bb74256c1640186a0'
BRIDGE = ROOT/'out/rowflow-bridge-detail/rowflow_bridge.dll'
BRIDGE_HASH = 'c5096fa3df305baf98a6027f38243e3410078ad316244e4469f5af492ab56d63'
LAYOUT_HASH = '0394a7b790c92db37aaa49190e213edc65914e79625f03d38d62cf3c2911da85'


def bridge():
    if DLL_SHA256 != LAYOUT_HASH or hashlib.sha256(BRIDGE.read_bytes()).hexdigest()!=BRIDGE_HASH:
        raise ValueError('RowFlow GPU bridge integrity mismatch')
    dll = ct.CDLL(str(BRIDGE))
    dll.live_texture_error.restype = ct.c_char_p
    dll.rowflow_copy_inputs.argtypes = [ct.c_void_p]*5
    dll.rowflow_publish.argtypes = [ct.c_void_p]*2+[ct.c_int]*3+[ct.c_void_p]
    return dll


def check(dll, result):
    if not result:
        raise RuntimeError(dll.live_texture_error().decode('utf-8','replace'))


@lru_cache(maxsize=1)
def implementation():
    options = dict(text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    if subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],**options).strip()!=REVISION:
        raise ValueError('RowFlow source revision mismatch')
    if subprocess.check_output(['git','-C',str(SOURCE),'status','--porcelain'],**options).strip():
        raise ValueError('RowFlow source must be clean')
    sys.path.insert(0,str(SOURCE))
    path = SOURCE/'iw3/models/row_flow_v3.py'
    spec = importlib.util.spec_from_file_location('depthsbs_rowflow_model',path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    from iw3.backward_warp import apply_divergence_nn_LR
    return module.RowFlowV3, apply_divergence_nn_LR


class RowFlowPool(LiveTexturePool):
    library_path = BRIDGE
    library_sha256 = BRIDGE_HASH


class RowFlowRenderer(LiveSourceGpuCandidate):
    def __init__(self,width,height,policy,engine,*,native=False,diagnostic=False,stop=None):
        self.pool = None
        self.model = self.compiled = self.rgb = self.aligned = None
        self.native, self.slot = native, None
        self.rowflow_ms = 0.0
        if policy.depth_backend!='da2-base' or not 0 < policy.divergence*100 <= 5:
            raise ValueError('RowFlow 시험은 Base와 입체 강도 5% 이하에서 지원합니다.')
        super().__init__(width,height,policy,engine)
        try:
            self.bridge = bridge()
            torch = engine.torch
            if torch.__version__!='2.7.1+cu128':
                raise ValueError('RowFlow experiment requires the validated PyTorch 2.7.1+cu128')
            import importlib.metadata
            if importlib.metadata.version('triton-windows')!='3.3.1.post21':
                raise ValueError('RowFlow experiment requires Triton Windows 3.3.1.post21')
            os.environ['TORCHINDUCTOR_CACHE_DIR'] = str(ROOT/'out/rowflow-compile-cache/inductor')
            os.environ['TRITON_CACHE_DIR'] = str(ROOT/'out/rowflow-compile-cache/triton')
            os.environ['TORCHINDUCTOR_COMPILE_THREADS'] = '1'
            torch.backends.cuda.matmul.allow_tf32 = False
            torch.backends.cudnn.allow_tf32 = False
            torch._dynamo.config.suppress_errors = False
            torch._dynamo.config.fail_on_recompile_limit_hit = True
            cls,self.warp = implementation()
            if hashlib.sha256(WEIGHT.read_bytes()).hexdigest()!=WEIGHT_HASH:
                raise ValueError('RowFlow weight integrity mismatch')
            checkpoint = torch.load(WEIGHT,map_location='cpu',weights_only=True)
            if checkpoint['name']!='sbs.row_flow_v3' or checkpoint['kwargs']!={}:
                raise ValueError('Unexpected RowFlow weight contract')
            with torch.cuda.stream(engine.stream),torch.inference_mode():
                self.model = cls().eval().to(f'cuda:{engine.device}')
                self.model.load_state_dict(checkpoint['state_dict'],strict=True)
                self.model.delta_output = self.model.symmetric = True
                self.compiled = torch.compile(self.model,dynamic=False,fullgraph=True)
                self.rgb = torch.zeros((height,width,3),device=f'cuda:{engine.device}',dtype=torch.uint8)
                self.aligned = torch.zeros((height,width),device=self.rgb.device,dtype=torch.float32)
                self.events = [torch.cuda.Event(enable_timing=True) for _ in range(2)]
                self._render_pixels()  # Compile before offering an output texture.
                engine.stream.synchronize()
            if stop is not None and stop.is_set():
                raise InterruptedError('RowFlow 준비를 취소했습니다.')
            if native:
                self.pool = RowFlowPool(width,height,diagnostic=diagnostic,layout=policy.stereo_layout)
        except BaseException as primary:
            try:self.close()
            except Exception as cleanup:primary.add_note(str(cleanup))
            raise

    def _render_pixels(self, *, compiled=True):
        torch = self.engine.torch
        if not bool(torch.isfinite(self.aligned).all()):
            raise ValueError('Nonfinite depth supplied to RowFlow')
        color = self.rgb.permute(2,0,1)[None].float().div(255)
        left,right = self.warp(self.compiled if compiled else self.model,color,self.aligned[None,None],
            self.policy.divergence*100,self.policy.convergence,steps=1,enable_amp=True)
        if not bool(torch.isfinite(left).all() & torch.isfinite(right).all()):
            raise ValueError('RowFlow produced nonfinite output')
        # Standard LR packing. The former swap matched a reversed CUDA baseline.
        return torch.cat((left,right),3).clamp(0,1).mul(255).round().to(torch.uint8)[0].permute(1,2,0).contiguous()

    def _project(self,frame,refined):
        torch = self.engine.torch
        invalid = ct.c_int()
        try:
            with torch.cuda.stream(self.engine.stream),torch.inference_mode():
                check(self.bridge,self.bridge.rowflow_copy_inputs(self.handle,self.rgb.data_ptr(),self.aligned.data_ptr(),
                    refined.ctypes.data if refined is not None else None,ct.byref(invalid)))
                self.d2h += 4
                self.syncs += 1
                if invalid.value:
                    raise ValueError('Nonfinite depth supplied to RowFlow')
                self.events[0].record(self.engine.stream)
                pixels = self._render_pixels()
                self.d2h += 2  # Two scalar finite reductions read by Python.
                self.syncs += 2
                self.events[1].record(self.engine.stream)
                if self.native:
                    self.pool.owner()
                    if type(self.slot) is not int or self.slot not in (0,1):
                        raise ValueError('RowFlow producer must own a writable slot')
                    check(self.bridge,self.bridge.rowflow_publish(self.pool.handle,pixels.data_ptr(),self.width*2,
                        self.height,self.slot,self._stream(self.engine)))
                    result = self.slot
                else:
                    result = pixels.cpu().numpy()
                    self.d2h += result.nbytes
                self.engine.stream.synchronize()
                self.syncs += 1
                self.rowflow_ms = self.events[0].elapsed_time(self.events[1])
                return result
        except BaseException:
            self.failed = True
            raise

    def _read_projection_times(self):
        # Existing slots describe splat/resolve/copies, not learned rendering.
        self.projection_ms.fill(0)

    def _pack_result(self,projected):
        return projected

    def close(self):
        if hasattr(self,'thread'):
            import threading
            if threading.get_ident()!=self.thread:
                raise RuntimeError('RowFlow close from another thread')
        error = None
        try:
            if self.pool is not None:self.pool.close()
        except Exception as exc:error=exc
        try:super().close()
        except Exception as exc:
            if error is None:error=exc
            else:error.add_note(str(exc))
        finally:
            self.pool = self.compiled = self.model = self.rgb = self.aligned = None
        if error is not None:raise error
