"""Test-only worker entry point for the production-source promotion candidate."""

import hashlib
import json

from .desktop_jobs import ROOT
from .live_sbs import sbs_worker as base_sbs_worker


CANDIDATE_DLL_SHA256 = (
    "f67fc53ccaa37a29474ba90bac80d3cb2bff12e8c685a24df9f7382db0c00fa7"
)
CANONICAL_SOURCE_SHA256 = (
    "3edbd99d2de91266801ebe921fc3ebfcf35849686de84f9789bc738229b64119"
)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate_manifest():
    root = ROOT / "out/live-depth-guide-promoted"
    dll = root / "live_depth.dll"
    manifest_path = root / "build-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    expected = {
        "dll_sha256": CANDIDATE_DLL_SHA256,
        "source_sha256": CANONICAL_SOURCE_SHA256,
    }
    actual = {key: str(manifest[key]).lower() for key in expected}
    if actual != expected or sha256(dll) != CANDIDATE_DLL_SHA256:
        raise ValueError("Production-source guide candidate artifact changed")
    return {
        "name": "production-source-guide-promotion-candidate",
        "dll": str(dll),
        "dll_sha256": CANDIDATE_DLL_SHA256,
        "canonical_source_sha256": CANONICAL_SOURCE_SHA256,
        "build_manifest": str(manifest_path),
        "build_manifest_sha256": sha256(manifest_path),
    }


def sbs_worker_promoted(*args, **kwargs):
    """Install the fixed candidate inside the owned child, then run production logic."""
    candidate = candidate_manifest()
    from . import live_gpu_candidate as gpu_module

    gpu_module.DLL_PATH = ROOT / "out/live-depth-guide-promoted/live_depth.dll"
    gpu_module.DLL_SHA256 = candidate["dll_sha256"]
    from . import live_gpu_texture as texture_module

    texture_module.DLL_SHA256 = candidate["dll_sha256"]
    texture_module.BORROWED_LAYOUT_SHA256 = candidate["dll_sha256"]
    return base_sbs_worker(*args, **kwargs)
