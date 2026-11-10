# oVDA runtime comparison, NC-SA-UHDV1.0; see LICENSE/README.md.
"""Explicit pinned pre-cleanup source for local A/B; never a runtime fallback."""
import hashlib
import importlib.util
import sys
from unittest.mock import patch
from depthsbs_app import ovda
from depthsbs_app.desktop_jobs import ROOT

REFERENCE=ROOT/'out/ovda-runtime-cleanup-20261109/reference/device_depth.py'
REFERENCE_SHA256='e104fd8fc1e4763e50bd09d0afc83a60732c37239193997fd56a56f74be45af7'


def reference_class():
    ovda.runtime_class(True)
    if hashlib.sha256(REFERENCE.read_bytes()).hexdigest()!=REFERENCE_SHA256:
        raise ValueError('Runtime comparison reference changed')
    name='_depthsbs_ovda.device_depth_before_cleanup'
    if name not in sys.modules:
        spec=importlib.util.spec_from_file_location(name,REFERENCE)
        module=importlib.util.module_from_spec(spec)
        sys.modules[name]=module
        spec.loader.exec_module(module)
    return sys.modules[name].OvdaDeviceTrt


def runtime_sbs_worker(variant,*args,**kwargs):
    from trial_runtime import trial_sbs_worker
    kwargs['gpu_capture_snapshot']=True
    current=ovda.runtime_class(True)
    if variant not in ('runtime-before','runtime-after'):raise ValueError('Unknown runtime comparison')
    selected=reference_class() if variant=='runtime-before' else current
    # Override only the explicit device-depth constructor in this owned child.
    original=ovda.runtime_class
    with patch.object(ovda,'runtime_class',lambda device_depth=False:selected if device_depth else original(False)):
        return trial_sbs_worker('fp32-current',*args,**kwargs)
