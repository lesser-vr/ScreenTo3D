"""Test-process-only adapter for two locally built, pinned FP16 plans.

Not imported by normal desktop launch. No product allowlist is edited.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path

from screento3d_app.desktop_jobs import ROOT

ARTIFACTS = ROOT / 'out/base-trt-fp16-20261105'
PINS = {
    'mixed': ('0216c0493714c120ebe261d29eb10b3eadb52ca8fc5934192aa2dbf2570bd9bd', 200667716),
    'selective': ('74f88ca9fb9bbf92ced5713bd9ee98066629de620bb09d0925965da5760c5cf5', 208912108),
}
FP32_PROFILES = {
    (518, 896): ('93d5159282cc96ac2ea79895051f7646514791cac9351917c62f444818b78209', 402367692),
    (518, 924): ('e5b17445993602abf2a01c0f6e7686d5fa67afec49bd9ef8bb4c133175c89d2e', 402660828),
}


def manifest(recipe):
    if recipe == 'fp32':
        return dict(recipe=recipe, runtime='tensorrt-fp32', plan_sha256='e5b17445993602abf2a01c0f6e7686d5fa67afec49bd9ef8bb4c133175c89d2e')
    digest, size = PINS[recipe]
    path = (ARTIFACTS / f'{recipe}.plan').resolve(strict=True)
    if (path.parent != ARTIFACTS.resolve(strict=True) or path.stat().st_size != size
            or hashlib.sha256(path.read_bytes()).hexdigest() != digest):
        raise ValueError('FP16 trial artifact integrity mismatch')
    return dict(recipe=recipe, runtime=f'tensorrt-fp16-{recipe}', plan=str(path),
                plan_sha256=digest, plan_bytes=size, model_shape=[1, 3, 518, 924])


@contextmanager
def installed(recipe):
    """Only inside an explicit trial process; restore module bindings afterward."""
    info = manifest(recipe)
    from screento3d_app import da2_base as base, da2_base_device as device
    if recipe == 'fp32':
        original = base.PROFILES, base.PRECISION
        try:
            base.PROFILES, base.PRECISION = FP32_PROFILES, 'fp32'
            yield info
        finally:
            base.PROFILES, base.PRECISION = original
        return
    old = base.checked_plan, base.profiles, base.PROFILES, device.Da2BaseDeviceEngine
    path = Path(info['plan'])
    def checked(directory, shape=(518, 896)):
        if Path(directory).resolve(strict=True) != ARTIFACTS.resolve(strict=True) or shape != (518, 924):
            raise ValueError('FP16 trial only supports its pinned 518x924 artifact')
        payload = path.read_bytes()
        if len(payload) != info['plan_bytes'] or hashlib.sha256(payload).hexdigest() != info['plan_sha256']:
            raise ValueError('FP16 trial plan changed before loading')
        return payload
    def profiles(directory):
        if Path(directory).resolve(strict=True) != (ROOT / 'out/da2-base-local').resolve(strict=True):
            raise ValueError('Unexpected Base directory in trial')
        checked(ARTIFACTS, (518, 924))
        return {(518, 924): ARTIFACTS}
    class TrialEngine(old[3]):
        def telemetry(self):
            return {**super().telemetry(), **info}
    try:
        base.checked_plan, base.profiles = checked, profiles
        base.PROFILES = {**old[2], (518, 924): PINS[recipe]}
        device.Da2BaseDeviceEngine = TrialEngine
        yield info
    finally:
        base.checked_plan, base.profiles, base.PROFILES, device.Da2BaseDeviceEngine = old


from screento3d_app.environment import required as app_env_required

def trial_worker(*args, **kwargs):
    from screento3d_app.live_sbs import sbs_worker
    recipe = app_env_required('SCREENTO3D_FP16_TRIAL')
    with installed(recipe):
        return sbs_worker(*args, **kwargs)


def write_manifest(path, recipe):
    path.write_text(json.dumps(manifest(recipe), indent=2), encoding='utf-8')
