"""Test-only worker entry point for retained mapped capture frames."""

import hashlib

from .desktop_jobs import ROOT
from .live_sbs import sbs_worker as base_sbs_worker


def candidate_manifest():
    paths = [
        ROOT / "v1/screento3d_app/capture_worker.py",
        ROOT / "v1/screento3d_app/live_retained_capture.py",
    ]
    return {
        "name": "retained-mapped-capture-frame",
        "sources": {
            str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths
        },
        "scope": (
            "Same-process WGC mapped-frame ownership transfer into one latest-frame "
            "slot; downstream RGB conversion and GPU path are unchanged"
        ),
    }


def sbs_worker_retained_capture(*args, **kwargs):
    """Install the opt-in transport inside the owned child process."""
    candidate_manifest()
    from .live_retained_capture import install

    install()
    return base_sbs_worker(*args, **kwargs)
