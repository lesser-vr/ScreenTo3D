"""Identity and user-bound build records for locally generated TensorRT plans."""

from .messages import Message as M
import ctypes as ct
import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path

TRT_VERSION = '11.2.1.2'
VDA_FP32_PACK = '691bc8c7795004d9f5ee8229391af28781301c8cdd7a7dc38c508a7c7a2d5f44'
VDA_ENCODER_PACK = 'd99ad9d3a3e40454b1726ccd304701dd9815ce3e846a9cdd400f25cf8d979f0d'


@lru_cache(maxsize=16)
def device_identity(index=0):
    # The desktop selects the first visible CUDA device; workers check their active ordinal.
    # No CUDA context, Torch import, or GPU allocation in the desktop process.
    drv = ct.WinDLL(str(Path(os.environ['SystemRoot'])/'System32/nvcuda.dll'))
    ordinal, driver, major, minor = (ct.c_int() for _ in range(4))
    uuid, name = (ct.c_ubyte * 16)(), ct.create_string_buffer(256)
    for func, args in [
        ('cuInit', (0,)), ('cuDeviceGet', (ct.byref(ordinal), index)),
        ('cuDeviceGetUuid', (uuid, ordinal)), ('cuDriverGetVersion', (ct.byref(driver),)),
        ('cuDeviceGetName', (name, len(name), ordinal)),
        ('cuDeviceGetAttribute', (ct.byref(major), 75, ordinal)),
        ('cuDeviceGetAttribute', (ct.byref(minor), 76, ordinal)),
    ]:
        if getattr(drv, func)(*args):
            raise RuntimeError(M('Check that an NVIDIA CUDA GPU and a working driver are available.'))
    return dict(uuid=bytes(uuid).hex(), gpu=name.value.decode(), compute_capability=[major.value, minor.value],
                cuda_driver=driver.value, tensorrt=TRT_VERSION)


def device_key(identity):
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]


class Blob(ct.Structure):
    _fields_ = [('size', ct.c_uint32), ('data', ct.c_void_p)]


def _dpapi(data, *, protect):
    buf = ct.create_string_buffer(data)
    source, dest = Blob(len(data), ct.cast(buf, ct.c_void_p)), Blob()
    crypto = ct.WinDLL('crypt32', use_last_error=True)
    call = crypto.CryptProtectData if protect else crypto.CryptUnprotectData
    if not call(ct.byref(source), None, None, None, None, 1, ct.byref(dest)):
        raise ValueError(M('Cannot verify the local engine build record. Reinstall the model.'))
    try:
        return ct.string_at(dest.data, dest.size)
    finally:
        ct.windll.kernel32.LocalFree(ct.c_void_p(dest.data))


def save_record(path, data):
    path.write_bytes(_dpapi(json.dumps(data, sort_keys=True).encode(), protect=True))


def local_record(folder, key):
    """Arbitrary import directories must continue through the legacy pinned loader."""
    from .optional_models import PACKS, model_root
    folder = Path(folder).resolve()
    revision = model_root(key).resolve()
    source, suffix = PACKS[key].sha, 'fp16'
    if not folder.is_relative_to(revision):
        if key != 'vda-small':
            return None
        for source, suffix in ((VDA_FP32_PACK, 'fp32'), (VDA_ENCODER_PACK, 'fp16')):
            old = revision.parent / source[:16]
            if folder.is_relative_to(old):
                revision = old
                break
        else:
            return None
    device = device_identity()
    root = revision / device_key(device)
    if folder.parent != root or folder.name not in {f'518x{w}-{suffix}' for w in (896, 924)}:
        raise ValueError(M('Install a local model engine compatible with this GPU.'))
    receipt = root/'build.receipt'
    if receipt.resolve().parent != root or receipt.stat().st_size > 65536:
        raise ValueError('Invalid local build record')
    record = json.loads(_dpapi(receipt.read_bytes(), protect=False))
    if record['source'] != source or record['device'] != device:
        raise ValueError(M('The GPU or TensorRT configuration changed. Reinstall the model.'))
    return record['profiles'][folder.name]
