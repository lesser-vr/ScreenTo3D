"""Bundled GPU preview boundary with no development-DLL or CPU fallback."""
from cuda_projection_experiment import CudaProjection
from .resources import resource_path


def preview_factory(width, height):
    path = resource_path('projection/projection.dll').resolve(strict=True)
    try:
        projection = CudaProjection(width, height, dll_path=path)
    except (OSError, RuntimeError) as error:
        raise RuntimeError(
            'GPU preview unavailable: requires compute capability 12.0 and CUDA '
            'driver API 13.1 or newer. Only RTX 5090 has been tested. '
            'Use the separate CPU-stereo DepthSBS package if unsupported. '
            f'No automatic fallback. Details: {error}'
        ) from error
    projection.algorithm = 'forward_zbuffer_cuda_preview'
    return projection
