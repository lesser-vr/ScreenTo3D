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


def copy(src, dst, *, package_root=None, excluded=None):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        def ignore(directory,names):
            from depthsbs_app.portable_package import exclusion
            rejected=[]
            for name in names:
                source=Path(directory)/name
                target=dst/source.relative_to(src)
                reason=exclusion(target.relative_to(package_root),is_dir=source.is_dir()) if package_root else ('bytecode' if name=='__pycache__' or name.endswith('.pyc') else '')
                if reason:
                    rejected.append(name)
                    if excluded is not None:
                        files=list(p for p in source.rglob('*') if p.is_file()) if source.is_dir() else [source]
                        record=excluded.setdefault(reason,dict(files=0,bytes=0))
                        record['files']+=len(files);record['bytes']+=sum(p.stat().st_size for p in files)
            return rejected
        shutil.copytree(src,dst,ignore=ignore)
    else:
        shutil.copy2(src, dst)


CUDA_RUNTIME_SHA='352ba4ebe61e9a3b171f357a3daf5dd15b6af4a9857673ff893bd6fd2964c075'


def bundle_model_packs(stage,source=None):
    from depthsbs_app.optional_models import PACKS
    source=Path(source) if source else ROOT/'out/desktop-distribution/packs'
    selected={key:PACKS[key] for key in ('da2-base','vda-small')}
    for pack in selected.values():
        path=source/pack.filename
        if path.stat().st_size!=pack.size or digest(path)!=pack.sha:
            raise ValueError('Bundled model pack differs from trusted pin: '+pack.filename)
    for pack in selected.values():copy(source/pack.filename,stage/'packs'/pack.filename)
    return {key:dict(filename=pack.filename,bytes=pack.size,sha256=pack.sha) for key,pack in selected.items()}


def model_distribution(stage,origin=None,bundled=False,source=None):
    from depthsbs_app.optional_models import MODEL_ORIGIN,model_downloads
    downloads=model_downloads(origin if origin is not None else MODEL_ORIGIN)
    base=downloads['da2-base']['url'].rsplit('/',1)[0]
    (stage/'model-origin.txt').write_text(base+'\n',encoding='utf-8')
    return dict(bundled_model_packs=bundle_model_packs(stage,source) if bundled else {},
                model_pack_downloads={} if bundled else downloads)


def build(dest, python_zip, origin=None, *, full_runtime=False,cuda_runtime=None,bundled_components=False,export_runtime_packs=False,bundled_models=False):
    sys.path.insert(0, str(ROOT/'v1'))
    from depthsbs_app.portable_cuda import PINS
    from depthsbs_app import __version__
    from depthsbs_app.portable_package import validate_qt_source,QT_PROFILE,runtime_exclusion
    validate_qt_source(ROOT/'out/gui-python-deps/PySide6')
    import importlib.util
    spec=importlib.util.spec_from_file_location('depthsbs_translations',ROOT/'scripts/build-translations.py')
    translations=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(translations)
    translations.build()
    media_spec=importlib.util.spec_from_file_location('desktop_shared_ffmpeg',ROOT/'scripts/prepare-ffmpeg-shared.py')
    media_module=importlib.util.module_from_spec(media_spec);media_spec.loader.exec_module(media_module)
    media=ROOT/'out/ffmpeg-shared-9.0.1'
    media_metadata=media_module.prepare(media)
    bundled_components=bundled_components or full_runtime
    cuda_runtime=Path(cuda_runtime) if cuda_runtime else Path('C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v13.1/bin/x64/cudart64_13.dll')
    if digest(cuda_runtime)!=CUDA_RUNTIME_SHA:raise ValueError('CUDA 13.1 runtime identity mismatch')
    if not bundled_components and export_runtime_packs:
        spec=importlib.util.spec_from_file_location('desktop_component_packs',ROOT/'scripts/build-component-packs.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        module.build(dest.parent/'runtime-packs',media,cuda_runtime)
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
        excluded={}
        stage = Path(scratch)/'app'
        with ZipFile(python_zip) as archive:
            archive.extractall(stage/'python')
        (stage/'python/python313._pth').write_text(
            'python313.zip\n.\n../v1\n../packages\nimport site\n', encoding='ascii')
        copy(ROOT/'out/desktop-launcher/ScreenTo3D.exe', stage/'ScreenTo3D.exe')
        (stage/'desktop-portable').touch()
        model_info=model_distribution(stage,origin,bundled_models)
        for name, pin in PINS.items():
            rel = Path('out/portable-cuda')/name
            if digest(ROOT/rel) != pin:
                raise ValueError(f'Portable CUDA release pin mismatch: {name}')
            copy(ROOT/rel, stage/rel)
        runtime=ROOT/PREVIEW/'_internal/runtime'
        target=stage/PREVIEW/'_internal/runtime';target.mkdir(parents=True)
        if not full_runtime:
            from depthsbs_app.builder_resources import LAYOUT,CATALOG,verify
            pack_spec=importlib.util.spec_from_file_location('desktop_runtime_packs',ROOT/'scripts/build-runtime-packs.py')
            pack_module=importlib.util.module_from_spec(pack_spec);pack_spec.loader.exec_module(pack_module)
            verify(runtime,CATALOG['common'])
            if export_runtime_packs:pack_module.build(dest.parent/'runtime-packs')
        for path in runtime.iterdir():
            reason=runtime_exclusion(path.name)
            if reason:
                record=excluded.setdefault(reason,dict(files=0,bytes=0))
                record['files']+=1;record['bytes']+=path.stat().st_size
                continue
            if not full_runtime and path.name.startswith('nvinfer_builder_resource_sm'):continue
            if bundled_components:copy(path,target/path.name)
        if not full_runtime:
            (target/'builder-layout.json').write_text(json.dumps(LAYOUT),encoding='utf-8')
        if bundled_components:copy(cuda_runtime,stage/PREVIEW/'_internal/runtime/cudart64_13.dll')
        else:
            (target/'component-layout.json').write_text(json.dumps(dict(schema=1,component='trt-core')),encoding='utf-8')
            media_target=stage/PREVIEW/'_internal/ffmpeg';media_target.mkdir()
            (media_target/'component-layout.json').write_text(json.dumps(dict(schema=1,component='media-tools')),encoding='utf-8')
        for rel in [Path('v1/depthsbs_app'), Path('v1/cuda_projection_experiment.py'), small,
                    Path('out/gpu-capture/gpu_capture.dll'), Path('out/qt-native-delivery/qt_native_delivery.dll'),
                    Path('out/base-input/OPENCV-NOTICE.txt'), Path('out/static-sbs/OPENCV-NOTICE.txt')]:
            copy(ROOT/rel, stage/rel)
        if bundled_components:copy(media,stage/PREVIEW/'_internal/ffmpeg')
        else:copy(media/'licenses',stage/'licenses/FFmpeg')
        for name in ('THIRD_PARTY_NOTICES.txt', 'TENSORRT-LICENSE.txt', 'CUDA-EULA.txt'):
            copy(ROOT/PREVIEW/name, stage/'licenses'/name)
        copy(ROOT/'distribution/THIRD_PARTY_NOTICES.txt',stage/'licenses/THIRD_PARTY_NOTICES.txt')
        copy(ROOT/'out/da2-base-source/LICENSE', stage/'licenses/Apache-2.0.txt')
        copy(ROOT/'models/da2-small/model-manifest.json',stage/'licenses/da2-small-model-manifest.json')
        copy(ROOT/'out/vda-oracle-env/Lib/site-packages/torch-2.7.1+cu128.dist-info/LICENSE',stage/'licenses/PyTorch-LICENSE.txt')
        copy(ROOT/'distribution/DESKTOP-README.txt',stage/'README.txt')
        packages = {
            'out/gui-python-deps': ('PySide6*', 'shiboken6*'),
            'out/capture-python-deps': ('windows_capture*',),
            'out/v1-python-deps': ('cuda*', 'cv2', 'opencv*dist-info', 'numpy*', 'tensorrt*', 'packaging*'),
            'out/vda-oracle-env/Lib/site-packages': ('typing_extensions*',),
        }
        for folder, patterns in packages.items():
            for pattern in patterns:
                matches = list((ROOT/folder).glob(pattern))
                if not matches:
                    raise FileNotFoundError(f'{folder}/{pattern}')
                for src in matches:
                    copy(src, stage/'packages'/src.name,package_root=stage,excluded=excluded)
        metadata=dict(product='ScreenTo3D',product_version=__version__,
            source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            source_dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True)),
            packaging_exclusions=excluded,
            qt_deployment_profile=dict(version=QT_PROFILE['pyside_version'],bindings=QT_PROFILE['bindings'],libraries=QT_PROFILE['libraries']),
            tensorrt_builder_resources='full' if full_runtime else 'GPU-selected pinned sidecar packs' if export_runtime_packs else 'GPU-selected official downloads',
            desktop_components='bundled' if bundled_components else 'on-demand pinned packs' if export_runtime_packs else 'on-demand official downloads',
            ffmpeg=media_metadata,
            gpu_buffers='native CUDA; no Torch runtime',cuda_runtime_sha256=CUDA_RUNTIME_SHA,
            built_at_utc=datetime.now(timezone.utc).isoformat(),
            python='CPython 3.13.9 Windows x64 embeddable',python_zip_sha256=PYTHON_SHA,
            small_onnx_sha256=manifest['onnx_sha256'],portable_cuda_sha256=PINS,
            optional_models='DA2 Base and VDA Small '+('bundled ONNX packs' if bundled_models else 'pinned public model downloads')+'; NVIDIA VFG official download, default off',
            **model_info,upstream_downloads=['tensorrt','cuda','ffmpeg','vfg'])
        metadata['application_source_sha256']={p.relative_to(stage).as_posix():digest(p)
            for p in (stage/'v1/depthsbs_app').rglob('*') if p.is_file()}
        (stage/'build-manifest.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
        stage.rename(dest)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--python-zip', required=True, type=Path)
    parser.add_argument('--model-origin', help='HTTPS directory hosting the two pinned ONNX packs')
    parser.add_argument('--bundle-models',action='store_true',help='Include Base/VDA ONNX packs for optional offline delivery; default downloads public packs')
    parser.add_argument('--full-runtime',action='store_true',help='Include all runtime/GPU resources; add --bundle-models for fully offline delivery')
    parser.add_argument('--cuda-runtime',type=Path,help='Pinned CUDA 13.1 cudart64_13.dll (build input only)')
    parser.add_argument('--bundled-components',action='store_true',help='Keep common TensorRT and media tools in the app for offline delivery')
    parser.add_argument('--export-runtime-packs',action='store_true',help='Also export optional legacy offline runtime sidecars')
    args = parser.parse_args()
    build(args.output, args.python_zip, args.model_origin,full_runtime=args.full_runtime,cuda_runtime=args.cuda_runtime,bundled_components=args.bundled_components,export_runtime_packs=args.export_runtime_packs,bundled_models=args.bundle_models)
