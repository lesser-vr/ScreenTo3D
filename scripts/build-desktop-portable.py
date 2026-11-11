"""Assemble the current QML desktop and bundled Small from a prepared Windows checkout."""
import argparse
import hashlib
import json
import shutil
import sys
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = Path('out/gpu-preview/DepthSBS-GPU-Preview')
PYTHON_SHA = '91d828c2da3a029b41699e918674a0cb379c02cf20dab9c501306885f837402a'


def digest(path):
    with path.open('rb') as src:
        return hashlib.file_digest(src, 'sha256').hexdigest()


def copy(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    else:
        shutil.copy2(src, dst)


def build(dest, python_zip, origin):
    sys.path.insert(0, str(ROOT/'v1'))
    from depthsbs_app.portable_cuda import PINS
    from depthsbs_app import __version__
    import importlib.util
    spec=importlib.util.spec_from_file_location('depthsbs_translations',ROOT/'scripts/build-translations.py')
    translations=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(translations)
    translations.build()
    if dest.exists():
        raise ValueError('Choose a new output directory.')
    if origin and (urlsplit(origin).scheme != 'https' or not urlsplit(origin).hostname):
        raise ValueError('The model origin must be an HTTPS directory.')
    if digest(python_zip) != PYTHON_SHA:
        raise ValueError('Expected the official CPython 3.13.9 Windows x64 embeddable ZIP.')
    manifest = json.loads((ROOT/'models/da2-small/model-manifest.json').read_text())
    small = PREVIEW/'_internal/models/da2-small/model_fp16.onnx'
    if digest(ROOT/small) != manifest['onnx_sha256']:
        raise ValueError('Bundled DA2 Small identity mismatch.')
    subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                    '-File', str(ROOT/'scripts/build-desktop-launcher.ps1')], check=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest.parent) as scratch:
        stage = Path(scratch)/'app'
        with ZipFile(python_zip) as archive:
            archive.extractall(stage/'python')
        (stage/'python/python313._pth').write_text(
            'python313.zip\n.\n../v1\n../packages\nimport site\n', encoding='ascii')
        copy(ROOT/'out/desktop-launcher/ScreenTo3D.exe', stage/'ScreenTo3D.exe')
        (stage/'desktop-portable').touch()
        if origin:
            (stage/'model-origin.txt').write_text(origin, encoding='utf-8')
        for name, pin in PINS.items():
            rel = Path('out/portable-cuda')/name
            if digest(ROOT/rel) != pin:
                raise ValueError(f'Portable CUDA release pin mismatch: {name}')
            copy(ROOT/rel, stage/rel)
        for rel in [Path('v1/depthsbs_app'), Path('v1/cuda_projection_experiment.py'), small,
                    PREVIEW/'_internal/runtime', PREVIEW/'_internal/ffmpeg',
                    Path('out/gpu-capture/gpu_capture.dll'), Path('out/qt-native-delivery/qt_native_delivery.dll'),
                    Path('out/base-input/OPENCV-NOTICE.txt'), Path('out/static-sbs/OPENCV-NOTICE.txt')]:
            copy(ROOT/rel, stage/rel)
        for name in ('THIRD_PARTY_NOTICES.txt', 'TENSORRT-LICENSE.txt', 'CUDA-EULA.txt'):
            copy(ROOT/PREVIEW/name, stage/'licenses'/name)
        copy(ROOT/'distribution/THIRD_PARTY_NOTICES.txt',stage/'licenses/THIRD_PARTY_NOTICES.txt')
        copy(ROOT/'out/da2-base-source/LICENSE', stage/'licenses/Apache-2.0.txt')
        copy(ROOT/'models/da2-small/model-manifest.json',stage/'licenses/da2-small-model-manifest.json')
        copy(ROOT/'distribution/DESKTOP-README.txt',stage/'README.txt')
        packages = {
            'out/gui-python-deps': ('PySide6*', 'shiboken6*'),
            'out/capture-python-deps': ('windows_capture*',),
            'out/v1-python-deps': ('cuda*', 'cv2', 'opencv*dist-info', 'numpy*', 'tensorrt*', 'packaging*'),
            'out/vda-oracle-env/Lib/site-packages': ('torch', 'torchgen', 'torch-*.dist-info', 'typing_extensions*',
                'filelock*', 'fsspec*', 'networkx*', 'jinja2*', 'markupsafe*', 'sympy*', 'mpmath*', 'functorch'),
        }
        for folder, patterns in packages.items():
            for pattern in patterns:
                matches = list((ROOT/folder).glob(pattern))
                if not matches:
                    raise FileNotFoundError(f'{folder}/{pattern}')
                for src in matches:
                    copy(src, stage/'packages'/src.name)
        metadata=dict(product='ScreenTo3D',product_version=__version__,
            source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            source_dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True)),
            built_at_utc=datetime.now(timezone.utc).isoformat(),
            python='CPython 3.13.9 Windows x64 embeddable',python_zip_sha256=PYTHON_SHA,
            small_onnx_sha256=manifest['onnx_sha256'],portable_cuda_sha256=PINS,
            optional_models='DA2 Base and VDA Small local packs; NVIDIA VFG official download, default off')
        (stage/'build-manifest.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
        stage.rename(dest)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--python-zip', required=True, type=Path)
    parser.add_argument('--model-origin', help='HTTPS directory hosting the two pinned ONNX packs')
    args = parser.parse_args()
    build(args.output, args.python_zip, args.model_origin)
