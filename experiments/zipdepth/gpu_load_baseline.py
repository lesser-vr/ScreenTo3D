"""Pinned pre-optimization worker for matched measurements; never a fallback."""
from pathlib import Path

def worker(*args,**kwargs):
    return _worker(False,*args,**kwargs)

def guide_worker(*args,**kwargs):
    """Previous bitmap/paced product, before guide precision optimization."""
    return _worker(True,*args,**kwargs)

def _worker(guide,*args,**kwargs):
    from screento3d_app.live_gpu_candidate import LiveGpuCandidate
    from screento3d_app.live_gpu_texture import TextureOutputMixin
    from screento3d_app.live_texture_pool import LiveTexturePool
    from screento3d_app.live_small_gpu_input import LiveSmallGpuInput,LiveSmallGpuInputTexture
    from screento3d_app.live_sbs import sbs_worker
    from trial import installed
    root=Path(__file__).resolve().parents[2]
    LiveGpuCandidate.library_path=root/'out/live-depth-detail/live_depth.dll'
    LiveGpuCandidate.library_sha256='a712b91082de8e31fb7c35ab81cae51c5c4d6a1d31b014b486be410646516c40'
    TextureOutputMixin.borrowed_layout_sha256=LiveGpuCandidate.library_sha256
    LiveSmallGpuInput.library_path=root/'out/small-input-detail/small_input.dll'
    LiveSmallGpuInput.library_sha256='bebfc39715f120e03b6f6cc08a1c68f14892acd624e9ffc53d8861d0596116fb'
    LiveSmallGpuInputTexture.borrowed_layout_sha256=LiveSmallGpuInput.library_sha256
    LiveTexturePool.library_path=root/'out/live-texture-detail/live_texture_runtime.dll'
    LiveTexturePool.library_sha256='5a044937a451184f4d3b2aa45bdd01504f41f9cdb8bd89016aac85d0ea4eb08e'
    if guide:
        LiveGpuCandidate.library_path=root/'out/gpu-load-opt/live_depth.dll'
        LiveGpuCandidate.library_sha256='a1abad814853a74890214f8cc95e9be853f107a7479ab3aad1afb0fda441afee'
        TextureOutputMixin.borrowed_layout_sha256=LiveGpuCandidate.library_sha256
        LiveSmallGpuInput.library_path=root/'out/gpu-load-opt/small_input.dll'
        LiveSmallGpuInput.library_sha256='a641facccfb24e60fc86debfdce4db795926e7a1c81b9a5ac545f4f3df20b857'
        LiveSmallGpuInputTexture.borrowed_layout_sha256=LiveSmallGpuInput.library_sha256
        LiveTexturePool.library_path=root/'out/gpu-load-opt/live_texture_runtime.dll'
        LiveTexturePool.library_sha256='f6e71f9b19f496dd972a3c2b88943d4539924e63c374cbf149a5877a74d1715d'
    else:
        kwargs['output_hz']=0  # Old consumer-only pacing, unchanged GUI limit.
    with installed():return sbs_worker(*args,**kwargs)
