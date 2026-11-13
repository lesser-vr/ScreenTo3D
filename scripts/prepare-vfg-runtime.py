"""Stage the verified NVIDIA wheel's five DLLs and notices for local VFG use.

No network access, pip installation, system PATH change or redistribution claim.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'v1'))
from screento3d_app.vfg_runtime import PINS, SDK  # noqa: E402

WHEEL_SHA256 = '5aaf6a42bc6b6dbbf52fcb714194c994a6893cbbf7ada38bc2165a1f83e4a6fc'


def stage(wheel):
    with wheel.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != WHEEL_SHA256:
            raise ValueError('Official NVIDIA wheel checksum mismatch')
    # Validate everything before writing; never extract arbitrary ZIP paths.
    files = {}
    with zipfile.ZipFile(wheel) as archive:
        for relative, expected in PINS.items():
            name = Path(relative).name
            data = archive.read('nvvfx/libs/' + name)
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError('VFG DLL checksum mismatch: ' + name)
            files[relative] = data
        for info in archive.infolist():
            if '.dist-info/licenses/' in info.filename and not info.is_dir():
                files['licenses/' + Path(info.filename).name] = archive.read(info)
    files['licenses/NOTICE.txt'] = b'Licensed by NVIDIA Corporation under the NVIDIA Open Model License\n'
    manifest = dict(wheel_sha256=WHEEL_SHA256,
                    files={name: hashlib.sha256(data).hexdigest() for name, data in files.items()})
    # Existing installations are checked, not silently overwritten.
    for name, data in files.items():
        path = SDK / name
        if path.exists() and path.read_bytes() != data:
            raise ValueError('Existing VFG runtime differs: ' + name)
    for name, data in files.items():
        path = SDK / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(data)
    (SDK / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return SDK


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel', type=Path, required=True)
    print(stage(parser.parse_args().wheel))
