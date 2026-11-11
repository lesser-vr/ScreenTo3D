"""Trusted first-use component identities; loading never downloads implicitly."""
import json
from pathlib import Path
from .messages import ErrorMessage as E

CATALOG=json.loads(Path(__file__).with_suffix('.json').read_text(encoding='utf-8'))
if CATALOG['schema']!=1:raise ValueError('Invalid desktop runtime catalog')
PACKS=CATALOG['packs']
LAYOUT=dict(schema=1,components=['trt-core','media-tools'])


def deferred(directory,key):
    marker=Path(directory)/'component-layout.json'
    if not marker.is_file():return False
    if json.loads(marker.read_text(encoding='utf-8'))!=dict(schema=1,component=key):
        raise ValueError(E('E_COMPONENT_INTEGRITY'))
    return True


def validate_payload(key,directory):
    directory=Path(directory)
    actual={p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file() and p.name!='.verified'}
    if actual!=set(PACKS[key]['files']):raise ValueError(E('E_COMPONENT_INTEGRITY'))
    # verify() accepts root filenames only. Nested license paths are checked here.
    import hashlib
    for name,pin in PACKS[key]['files'].items():
        path=directory/name
        if path.is_symlink() or path.stat().st_size!=pin['bytes']:
            raise ValueError(E('E_COMPONENT_INTEGRITY'))
        with path.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
        if sha!=pin['sha256']:raise ValueError(E('E_COMPONENT_INTEGRITY'))


def resolve(directory,key):
    directory=Path(directory)
    from .optional_models import available,installed_path
    target=installed_path(key)
    if not deferred(directory,key) and directory.resolve()!=target.resolve():return directory
    if not available(key,target):raise ValueError(E('E_RUNTIME_REQUIRED' if key=='trt-core' else 'E_MEDIA_REQUIRED'))
    validate_payload(key,target)
    return target
