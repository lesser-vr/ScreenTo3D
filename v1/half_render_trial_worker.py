"""Explicit benchmark-only worker injection for the reduced stereo experiment."""
import hashlib
from depthsbs_app.desktop_jobs import ROOT

DLL = ROOT / "out/half-render-scratch/half_render_trial.dll"
SHA256 = "4e0392be615dadb42bbd2afa429c264bdaf689ba350b905111cb3e8467b99824"


def sbs_worker_trial(*args, **kwargs):
    if (kwargs.get("stereo_layout") not in ("half-sbs", "half-tb")
            or kwargs.get("vfg_enabled")
            or kwargs.get("renderer_snapshot") not in (None, "cuda")):
        raise ValueError("Half rendering trial requires a Half layout with VFG off")
    if hashlib.sha256(DLL.read_bytes()).hexdigest() != SHA256:
        raise ValueError("Half render trial checksum mismatch")
    from depthsbs_app.live_texture_pool import LiveTexturePool
    from depthsbs_app.live_sbs import sbs_worker
    LiveTexturePool.library_path = DLL
    LiveTexturePool.library_sha256 = SHA256
    return sbs_worker(*args, **kwargs)
