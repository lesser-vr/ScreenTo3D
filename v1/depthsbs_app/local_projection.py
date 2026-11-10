"""Explicit source-app CUDA projection using the validated local preview DLL."""
import hashlib
from pathlib import Path
from .portable_cuda import binary

DLL_SHA256 = 'e16e82674ad19373ecffc4d5ec8601f46bda359912200a941c3f29c743975114'


def checked_dll():
    root = Path(__file__).resolve().parents[2]
    path = root / 'out/gpu-preview/DepthSBS-GPU-Preview/_internal/projection/projection.dll'
    path, expected = binary(path, DLL_SHA256)
    if not path.is_file():
        raise ValueError('CUDA stereo is not installed: prepare the local GPU preview; or explicitly select CPU stereo')
    with path.open('rb') as source:
        if hashlib.file_digest(source, 'sha256').hexdigest() != expected:
            raise ValueError('CUDA stereo DLL checksum mismatch; no fallback or unvalidated DLL loading')
    return path.resolve(strict=True)


def factory(width, height):
    from cuda_projection_experiment import CudaProjection
    try:
        result = CudaProjection(width, height, dll_path=checked_dll())
    except (OSError, RuntimeError) as error:
        raise RuntimeError('CUDA stereo requires a compatible NVIDIA GPU and CUDA driver API 13.1+. '
                           'No CPU fallback. Select CPU explicitly if needed. ' + str(error)) from error
    result.algorithm = 'forward_zbuffer_cuda_local'
    return result
