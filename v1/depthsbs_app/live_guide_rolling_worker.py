"""Test-only worker entry point for the hash-pinned rolling guide candidate."""

import hashlib
import json

from .desktop_jobs import ROOT
from .live_sbs import sbs_worker as base_sbs_worker


CANDIDATE_DLL_SHA256 = (
    "c938bc431b6e8e29f4145b0c5fbe0ebc5f0f827ef187be217af1f59641376230"
)
CANDIDATE_SOURCE_SHA256 = (
    "73493e8d7feab5c3b2e0e17ba5974c7cbf1fd0693d4f05eed7b11a2ab8a9ace4"
)
CANONICAL_SOURCE_SHA256 = (
    "64b01cb4186bca30c8acfc7b445fc71baff210b3d26144a411bef567aec9033c"
)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate_manifest():
    root = ROOT / "out/live-depth-guide-rolling"
    dll = root / "live_depth.dll"
    manifest_path = root / "build-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    expected = {
        "dll_sha256": CANDIDATE_DLL_SHA256,
        "source_sha256": CANONICAL_SOURCE_SHA256,
        "candidate_source_sha256": CANDIDATE_SOURCE_SHA256,
    }
    actual = {key: str(manifest[key]).lower() for key in expected}
    if actual != expected or sha256(dll) != CANDIDATE_DLL_SHA256:
        raise ValueError("Rolling guide candidate artifact changed")
    return {
        "name": "rolling-window-isolated",
        "dll": str(dll),
        "dll_sha256": CANDIDATE_DLL_SHA256,
        "candidate_source_sha256": CANDIDATE_SOURCE_SHA256,
        "canonical_source_sha256": CANONICAL_SOURCE_SHA256,
        "build_manifest": str(manifest_path),
        "build_manifest_sha256": sha256(manifest_path),
    }


def sbs_worker_rolling(*args, **kwargs):
    """Install the fixed candidate inside the owned child, then run production logic."""
    candidate = candidate_manifest()
    from . import live_gpu_candidate as gpu_module

    gpu_module.DLL_PATH = ROOT / "out/live-depth-guide-rolling/live_depth.dll"
    gpu_module.DLL_SHA256 = candidate["dll_sha256"]
    # LiveGpuTexture's layout guard is imported by value. The candidate includes
    # the same canonical LiveDepth definition, verified above by source hash.
    from . import live_gpu_texture as texture_module

    texture_module.DLL_SHA256 = candidate["dll_sha256"]
    texture_module.BORROWED_LAYOUT_SHA256 = candidate["dll_sha256"]
    return base_sbs_worker(*args, **kwargs)
