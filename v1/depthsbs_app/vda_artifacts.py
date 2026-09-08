"""VDA artifact and fixed-profile validation; no CUDA/PyTorch imports."""
import hashlib
import json
from pathlib import Path

SCHEMA = 1
MODEL_ID = 'vda-small-streaming-fp32'
SHAPE = [1, 1, 3, 518, 896]
PROFILES = {'518x896': (518, 896), '518x924': (518, 924)}
SOURCE_REVISION = '4f5ae23172ba60fd7bc11ef671cca678842c7072'
WEIGHT_SHA256 = '13379300b739e659f076a59d52e9801bd8d38c541a7e71f73bbca4dcfb013609'


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def profile_shape(width, height):
    if type(width) is not int or type(height) is not int or not (16 <= width <= 4096 and 16 <= height <= 2160):
        raise ValueError('VDA source dimensions must be 16..4096 by 16..2160')
    if max(width, height) / min(width, height) > 1.78:
        raise ValueError('VDA profile requires an aspect ratio no wider than 1.78')
    scale = max(518 / width, 518 / height)
    # Same ties-to-even rounding as numpy.round in the pinned transform.
    return (max(518, round(height * scale / 14) * 14),
            max(518, round(width * scale / 14) * 14))


def validate_input(metadata, shape=(518, 896)):
    if tuple(shape) not in PROFILES.values() or profile_shape(metadata['width'], metadata['height']) != tuple(shape):
        raise ValueError(f'This VDA profile requires {shape[0]}x{shape[1]}; select the matching validated engine profile')


def cache_layout(shape):
    if tuple(shape) not in PROFILES.values():
        raise ValueError('Unsupported VDA cache profile')
    h, w = (value // 14 for value in shape)
    spatial = h * w
    half = ((h + 1) // 2) * ((w + 1) // 2)
    return [(spatial, 192)] * 2 + [(half, 384)] * 2 + [(spatial, 64)] * 2 + [(spatial * 4, 64)] * 2


def load_manifest(directory, verify_hashes=True):
    directory = Path(directory).resolve(strict=True)
    path = directory / 'manifest.json'
    if path.stat().st_size > 131072:
        raise ValueError('VDA manifest exceeds size limit')
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('VDA manifest must be an object')
    input_shape = data.get('input_shape')
    if not isinstance(input_shape, list) or len(input_shape) != 5 or any(type(value) is not int for value in input_shape):
        raise ValueError('VDA input shape must contain five integer dimensions')
    if (data.get('schema') != SCHEMA or data.get('model_id') != MODEL_ID or
            data.get('input_shape') not in [[1, 1, 3, *shape] for shape in PROFILES.values()] or data.get('source_revision') != SOURCE_REVISION or
            data.get('weight_sha256') != WEIGHT_SHA256):
        raise ValueError('Incompatible VDA artifact identity or profile')
    if data.get('tensorrt') != '11.2.1.2' or data.get('compute_capability') != [12, 0]:
        raise ValueError('Unsupported VDA TensorRT/device profile')
    if data.get('gpu') != 'NVIDIA GeForce RTX 5090':
        raise ValueError('VDA artifact was not validated for the supported GPU')
    if data.get('precision') != 'fp32' or data.get('fixes') != ['stable-temporal-softmax', 'constant-position-resize']:
        raise ValueError('VDA artifact lacks validated precision/export fixes')
    validation = data.get('validation', {})
    if (not isinstance(validation, dict) or validation.get('passed') is not True or
            type(validation.get('comparisons')) is not int or validation['comparisons'] < 585 or
            validation.get('atol') != 0.001 or validation.get('rtol') != 0.001):
        raise ValueError('VDA artifact has no accepted parity validation')
    if not isinstance(data.get('engines'), dict):
        raise ValueError('Invalid VDA engine records')
    for name in ('warmup', 'cached'):
        record = data['engines'].get(name, {})
        if not isinstance(record, dict) or record.get('file') != f'{name}.plan':
            raise ValueError('Invalid VDA engine filename')
        digest = record.get('sha256', '')
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('Invalid VDA engine digest')
        engine_path = (directory / record['file']).resolve(strict=True)
        if engine_path.parent != directory or not 1 <= engine_path.stat().st_size <= 2 * 1024**3:
            raise ValueError('Invalid VDA engine path or size')
        if verify_hashes and sha256(engine_path) != digest:
            raise ValueError('VDA engine checksum mismatch')
    return data


def artifact_profiles(directory):
    """Accept one artifact or an allowlisted, non-recursive trusted profile root."""
    directory = Path(directory).resolve(strict=True)
    if (directory / 'manifest.json').exists():
        manifest = load_manifest(directory)
        return {tuple(manifest['input_shape'][-2:]): directory}
    profiles = {}
    for name, shape in PROFILES.items():
        candidate = directory / f'{name}-fp32'
        if not candidate.exists():
            continue
        candidate = candidate.resolve(strict=True)
        if candidate.parent != directory:
            raise ValueError('VDA profile directory escapes the trusted root')
        manifest = load_manifest(candidate)
        if tuple(manifest['input_shape'][-2:]) != shape:
            raise ValueError('VDA profile folder and manifest dimensions disagree')
        profiles[shape] = candidate
    if not profiles:
        raise ValueError('No validated VDA profiles found in the selected directory')
    return profiles


def select_artifact(profiles, metadata):
    shape = profile_shape(metadata['width'], metadata['height'])
    if shape not in profiles:
        raise ValueError(f'No matching VDA engine for {shape[0]}x{shape[1]}; build/select that profile or explicitly choose DA2')
    return profiles[shape]
