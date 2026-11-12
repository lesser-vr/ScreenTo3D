"""Pinned, GPU-selected TensorRT builder resources for split portable layouts."""
import hashlib
import json
from functools import lru_cache
from pathlib import Path

from .messages import ErrorMessage as E

CATALOG=json.loads(Path(__file__).with_name('tensorrt_resources.json').read_text(encoding='utf-8'))
VERSION='11.2.1.2'
if CATALOG['schema']!=1 or CATALOG['version']!=VERSION:
    raise ValueError('Invalid bundled TensorRT resource catalog')
PACKS=CATALOG['packs']
LAYOUT=dict(schema=1,tensorrt=VERSION,resources='gpu-selected')


@lru_cache(maxsize=16)
def _local_verified(path,size,mtime,expected):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()==expected


def runtime_directory():
    from .desktop_jobs import BUNDLE
    return BUNDLE/'runtime'


def required_key(directory=None,device=None):
    directory=Path(directory) if directory is not None else runtime_directory()
    if not (directory/'builder-layout.json').is_file():return ''
    if device is None:
        from .engine_cache import device_identity
        device=device_identity()
    major,minor=device['compute_capability']
    key=f'trt-sm{major}{minor}'
    # Preserve the full upstream resource set for architectures without an exact
    # resource file; TensorRT itself determines whether that GPU is supported.
    return key if key in PACKS else 'trt-all'


def ready(key):
    from .optional_models import available,installed_path,source_for
    if available(key,installed_path(key)):return True
    if key!='trt-all' and available('trt-all',installed_path('trt-all')):return True
    try:source=source_for(key)
    except (FileNotFoundError,ValueError):return False
    if not isinstance(source,Path) or not source.is_file():return False
    info=source.stat();spec=PACKS[key]
    return info.st_size==spec['size'] and _local_verified(str(source),info.st_size,info.st_mtime_ns,spec['sha'])


def verify(directory,files):
    directory=Path(directory)
    for name,identity in files.items():
        path=directory/name
        if path.name!=name or not path.is_file() or path.stat().st_size!=identity['bytes']:
            raise ValueError(E('E_GPU_RUNTIME_INTEGRITY'))
        with path.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
        if actual not in (identity['sha256'],identity.get('upstream_sha256')):raise ValueError(E('E_GPU_RUNTIME_INTEGRITY'))


def validate_payload(key,directory):
    expected=PACKS[key]['files']
    actual={p.name for p in Path(directory).iterdir() if p.name!='.verified'}
    if actual!=set(expected):raise ValueError(E('E_GPU_RUNTIME_INTEGRITY'))
    verify(directory,expected)


def prepare(directory):
    """Return verified extra DLL directories; never downloads implicitly."""
    directory=Path(directory)
    if not (directory/'builder-layout.json').is_file():return []
    try:layout=json.loads((directory/'builder-layout.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):raise ValueError(E('E_GPU_RUNTIME_LAYOUT')) from None
    if layout!=LAYOUT:raise ValueError(E('E_GPU_RUNTIME_LAYOUT'))
    key=required_key(directory)
    verify(directory,CATALOG['common'])
    from .optional_models import available,installed_path,source_for,install
    target=installed_path(key)
    if not available(key,target):
        full=installed_path('trt-all')
        if key!='trt-all' and available('trt-all',full):
            validate_payload('trt-all',full);return [full]
        try:source=source_for(key)
        except (FileNotFoundError,ValueError):raise ValueError(E('E_GPU_RUNTIME_REQUIRED')) from None
        if not isinstance(source,Path):raise ValueError(E('E_GPU_RUNTIME_REQUIRED'))
        target=install(key,source,target,lambda *_:None,lambda:False)
    verify(target,PACKS[key]['files'])
    return [target]
