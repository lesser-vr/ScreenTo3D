"""Test-only worker entry point for page-locked native RGB staging."""

import hashlib

from .desktop_jobs import ROOT
from .live_sbs import sbs_worker as base_sbs_worker


def candidate_manifest():
    from .live_gpu_candidate import DLL_PATH, DLL_SHA256

    if hashlib.sha256(DLL_PATH.read_bytes()).hexdigest() != DLL_SHA256:
        raise ValueError("Pinned input candidate product DLL changed")
    return {
        "name": "page-locked-rgb-staging",
        "dll": str(DLL_PATH),
        "dll_sha256": DLL_SHA256,
        "candidate_source": str(ROOT / "v1/depthsbs_app/live_pinned_input.py"),
        "candidate_source_sha256": hashlib.sha256(
            (ROOT / "v1/depthsbs_app/live_pinned_input.py").read_bytes()
        ).hexdigest(),
    }


def sbs_worker_pinned_input(*args, **kwargs):
    """Install the opt-in class inside the owned child process."""
    candidate_manifest()
    from .live_pinned_input import LiveGpuPinnedTexture
    from . import live_gpu_texture as texture_module

    texture_module.LiveGpuTexture = LiveGpuPinnedTexture
    return base_sbs_worker(*args, **kwargs)
