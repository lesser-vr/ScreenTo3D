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
    scale = max(518 / width, 518 / height)
    # Same ties-to-even rounding as numpy.round in the pinned transform.
    return (max(518, round(height * scale / 14) * 14),
            max(518, round(width * scale / 14) * 14))


def validate_input(metadata, shape=(518, 896)):
    """Exact upstream transform required by the artifact parity/build tools."""
    if tuple(shape) not in PROFILES.values() or native_profile(metadata['width'], metadata['height']) != tuple(shape):
        raise ValueError(f'This VDA profile requires {shape[0]}x{shape[1]}; select the matching validated engine profile')


def native_profile(width, height):
    shape = profile_shape(width, height)
    if shape in PROFILES.values() and max(width, height) / min(width, height) <= 1.78:
        return shape
    return None


def content_rect(width, height, shape):
    """Top, left, height and width of the source inside a VDA inference canvas."""
    shape = tuple(shape)
    if shape not in PROFILES.values():
        raise ValueError('Unsupported VDA canvas')
    native = native_profile(width, height)
    h, w = shape
    if native is not None:
        if native != shape:
            raise ValueError('Select the matching validated VDA profile')
        return 0, 0, h, w
    scale = min(w / width, h / height)
    rh, rw = max(1, round(height * scale)), max(1, round(width * scale))
    return (h-rh)//2, (w-rw)//2, rh, rw


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
    from .engine_cache import local_record
    from .optional_models import model_root
    record = local_record(directory, 'vda-small')
    if record is not None:
        for name in ('warmup', 'cached'):
            engine = (directory / f'{name}.plan').resolve(strict=True)
            pin = record['engines'][name]
            if (engine.parent != directory or engine.stat().st_size != pin['bytes']
                    or (verify_hashes and sha256(engine) != pin['sha256'])):
                raise ValueError('Local VDA engine checksum mismatch')
        return record
    legacy = model_root('vda-small').parent/'df79608a991fa734'
    if directory.parent == legacy.resolve():
        trusted = {
            '518x896-fp32': 'f85ae09668af4af389bbf962aafe1e52d1ffb9104e175101895971c791148bcb',
            '518x924-fp32': 'c9829b7f0084ee62e23f8d332d41504b751c5c7c5ab1b8a6677eba1276e4b288',
        }
        if path.stat().st_size != 1071 or sha256(path) != trusted.get(directory.name):
            raise ValueError('Installed VDA manifest differs from the pinned release.')
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


def uses_mixed_fp16(directory):
    from .optional_models import model_root
    from .engine_cache import VDA_ENCODER_PACK
    root = model_root('vda-small').resolve()
    path = Path(directory).resolve()
    return path.is_relative_to(root) or path.is_relative_to(root.parent / VDA_ENCODER_PACK[:16])


def artifact_profiles(directory):
    """Accept one artifact or an allowlisted, non-recursive trusted profile root."""
    directory = Path(directory).resolve(strict=True)
    if (directory / 'manifest.json').exists() or (directory / 'warmup.plan').is_file():
        manifest = load_manifest(directory)
        return {tuple(manifest['input_shape'][-2:]): directory}
    profiles = {}
    suffix = 'fp16' if uses_mixed_fp16(directory) else 'fp32'
    for name, shape in PROFILES.items():
        candidate = directory / f'{name}-{suffix}'
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
    width, height = metadata['width'], metadata['height']
    shape = native_profile(width, height)
    if shape is not None:
        if shape not in profiles:
            raise ValueError(f'No matching VDA engine for {shape[0]}x{shape[1]}; build/select that profile or explicitly choose DA2')
        return profiles[shape]
    if not profiles:
        raise ValueError('No validated VDA profiles available')

    def occupancy(canvas):
        _, _, h, w = content_rect(width, height, canvas)
        return h*w / (canvas[0]*canvas[1])

    return profiles[max(profiles, key=occupancy)]
