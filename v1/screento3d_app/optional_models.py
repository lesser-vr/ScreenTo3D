"""Pinned optional downloads. Only a fully verified installation becomes visible."""
from .messages import ErrorMessage as E

from .messages import Message as M
from .messages import decode_message
import hashlib
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZipFile

from .desktop_jobs import ROOT
from .user_data import data_root

MODEL_REPOSITORY = 'lesser-vr/ScreenTo3D-Models'
MODEL_RELEASE = 'packs-2026.11.1'
MODEL_ORIGIN = f'https://github.com/{MODEL_REPOSITORY}/releases/download/{MODEL_RELEASE}'


@dataclass(frozen=True)
class Pack:
    name: str
    filename: str
    size: int
    sha: str
    terms: str


PACKS = {
    'da2-base': Pack('DA2 Base', 'da2-base-onnx-v1.zip', 392348171,
                     '61bf0969e59e0b098ad4f968522b990d844ff7e4a0654dd82bbadfcd6b054731',
                     M("Optimized for this PC's NVIDIA GPU · CC BY-NC 4.0 non-commercial use")),
    'vda-small': Pack('VDA Small', 'vda-small-onnx-v3.zip', 363291834,
                      'b4e68c45328e37b601c95f1d06a024c41c510c6c980ba2fcdec5b1030603778f',
                      M("Optimized for this PC's NVIDIA GPU · Apache 2.0")),
    'vfg': Pack('NVIDIA VFG', 'nvidia_vfx-0.2.0.0-cp311-cp311-win_amd64.whl', 435809365,
                '5aaf6a42bc6b6dbbf52fcb714194c994a6893cbbf7ada38bc2165a1f83e4a6fc',
                M('NVIDIA VFX · NVIDIA software and model terms apply')),
}
from .builder_resources import PACKS as BUILDER_PACKS
PACKS.update({key:Pack('TensorRT '+key.removeprefix('trt-').upper(),item['filename'],item['size'],item['sha'],
    M('GPU engine builder · NVIDIA terms apply')) for key,item in BUILDER_PACKS.items()})
from .desktop_runtimes import PACKS as COMPONENT_PACKS
PACKS.update({key:Pack('TensorRT' if key=='trt-core' else 'FFmpeg',item['filename'],item['size'],item['sha'],
    M('Required for live 3D and file conversion') if key=='trt-core' else M('Required for file conversion'))
    for key,item in COMPONENT_PACKS.items()})


GRAPH_HASHES = {
    'da2-base': {
        896: {'model': 'a955082568d50df8b5e140ce0d62ab67beebcb8c25f9ffd87d067c8a027430e1'},
        924: {'model': '7246031b12c9cfb5d1007e715da05f9472241937fce795e6013727723a57323f'},
    },
    'vda-small': {
        896: {'warmup': '13361c3f0e32cae6825b3a63172e3325517f17d13e0c17082976df114bda7a84',
              'cached': 'dd31fa65c597761ab199a91f74f851c262a9d1fcdf68a17ed8550f9eecee3112'},
        924: {'warmup': 'a5070181d508da47f0f3c25d6a34554da05d591d0dedaa1c4801b2a2ad2bccf5',
              'cached': '4faadb5fc59ed3217e4ed149969f7dd33bca13ae2d17146b4a975ef36332dab5'},
    },
}


def model_downloads(origin=MODEL_ORIGIN):
    """Exact model identities; remote metadata never authorizes new bytes."""
    base=origin.strip().rstrip('/')
    if urlsplit(base).scheme != 'https' or not urlsplit(base).hostname:
        raise ValueError(E('E_MODEL_URL_INVALID'))
    return {key:dict(url=base+'/'+PACKS[key].filename,size=PACKS[key].size,sha256=PACKS[key].sha)
            for key in GRAPH_HASHES}


def model_root(key):
    return data_root() / 'models' / key / PACKS[key].sha[:16]


def installed_path(key):
    from .engine_cache import device_identity, device_key
    root = model_root(key)
    return root / device_key(device_identity()) if key in GRAPH_HASHES else root


def available(key, directory):
    """Cheap inventory only. Workers still validate the actual artifact on use."""
    if key not in PACKS or not directory:
        return False
    path = Path(directory)
    if key in COMPONENT_PACKS:
        return ((path/'.verified').is_file() and all((path/name).is_file() for name in COMPONENT_PACKS[key]['files']))
    if key in BUILDER_PACKS:
        return ((path/'.verified').is_file() and all((path/name).is_file() for name in BUILDER_PACKS[key]['files']))
    from .engine_cache import VDA_ENCODER_PACK, VDA_FP32_PACK
    old_vda = key == 'vda-small' and path.is_relative_to(model_root(key).parent / VDA_FP32_PACK[:16])
    encoder_vda = key == 'vda-small' and path.is_relative_to(model_root(key).parent / VDA_ENCODER_PACK[:16])
    if key in GRAPH_HASHES and (path.is_relative_to(model_root(key)) or old_vda or encoder_vda):
        names = ('model.plan',) if key == 'da2-base' else ('warmup.plan', 'cached.plan')
        suffix = 'fp32' if old_vda else 'fp16'
        return ((path/'build.receipt').is_file() and (path/'.verified').is_file()
                and all((path/f'518x{w}-{suffix}'/n).is_file() for w in (896, 924) for n in names))
    if key == 'vfg':
        from .vfg_runtime import PINS
        return all((path / name).is_file() for name in PINS)
    if key == 'da2-base':
        return (path / 'model.plan').is_file() or any(
            (path / f'518x{w}-fp16/model.plan').is_file() for w in (896, 924))
    return any(all((folder / name).is_file() for name in ('manifest.json', 'warmup.plan', 'cached.plan'))
               for folder in (path, path/'518x896-fp32', path/'518x924-fp32'))


def source_for(key):
    pack = PACKS[key]
    if key == 'vfg':
        return 'https://pypi.nvidia.com/nvidia-vfx/' + pack.filename
    category='runtime-packs' if key in BUILDER_PACKS or key in COMPONENT_PACKS else 'packs'
    folders=(ROOT/category,ROOT.parent/category,ROOT/'out/desktop-distribution'/category)
    # Bundled models and original offline packs require no network source.
    for folder in folders:
        if (folder/pack.filename).is_file():return folder/pack.filename
    if key in BUILDER_PACKS or key in COMPONENT_PACKS:
        from .official_sources import OfficialSource
        return OfficialSource(key)
    # A distributor supplies the origin together with the desktop build. The
    # origin cannot change the digest or the engine version the app accepts.
    origin = ROOT / 'model-origin.txt'
    base = origin.read_text(encoding='utf-8') if origin.is_file() else MODEL_ORIGIN
    return model_downloads(base)[key]['url']


def optimize(key, payload, cancelled):
    error = payload.parent/'build-error.txt'
    cmd = [sys.executable, '-m', 'screento3d_app.build_local_engine', key, str(payload), str(error)]
    with subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL) as child:
        try:
            while child.poll() is None:
                if cancelled():
                    raise InterruptedError(E('E_INSTALL_CANCELLED'))
                try:
                    child.wait(timeout=0.2)
                except subprocess.TimeoutExpired:
                    continue
            if child.returncode:
                reason = decode_message(error.read_text(encoding='utf-8')) if error.is_file() else M('Exit code {v0}', v0=child.returncode)
                raise RuntimeError(E('E_ENGINE_OPTIMIZATION',reason=reason))
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()


def install(key, source, target, progress, cancelled):
    from .official_sources import OfficialSource,populate
    from .download_cache import fetch
    pack = PACKS[key]
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    def check():
        if cancelled():
            raise InterruptedError(E('E_INSTALL_CANCELLED'))

    with tempfile.TemporaryDirectory(prefix='.install-', dir=target.parent) as scratch:
        archive = Path(scratch) / pack.filename
        payload = Path(scratch) / 'ready'
        payload.mkdir()
        expanded=sum(p['bytes'] for p in COMPONENT_PACKS[key]['files'].values()) if key in COMPONENT_PACKS else pack.size
        required = pack.size*4 if key in GRAPH_HASHES else pack.size+expanded+16*1024**2
        if shutil.disk_usage(scratch).free < required:
            raise OSError(E('E_INSTALL_SPACE_REQUIRED', v0=required / 1e9))
        check()
        if isinstance(source,OfficialSource):
            populate(source,payload,progress,cancelled)
        else:
            if not isinstance(source,Path):
                archive=fetch(pack.filename,source,pack.size,pack.sha,progress,cancelled)
            else:
                _copy_verified_archive(source,archive,pack,progress,check)
            _extract_archive(key,archive,payload,check)
        if key == 'vfg':
            (payload/'licenses/NOTICE.txt').write_text(
                'Licensed by NVIDIA Corporation under the NVIDIA Open Model License\n', encoding='utf-8')
        elif key in BUILDER_PACKS:
            from .builder_resources import validate_payload
            validate_payload(key,payload)
        elif key in COMPONENT_PACKS:
            from .desktop_runtimes import validate_payload
            validate_payload(key,payload)
        else:
            check()
            progress(M('Optimizing and validating the engine for this GPU…'), -1)
            optimize(key, payload, cancelled)
        check()
        try:
            (payload / '.verified').write_text(pack.sha, encoding='ascii')
            payload.rename(target)
        except OSError:
            # Another process may have installed this exact immutable revision.
            mark = target / '.verified'
            if not available(key, target) or not mark.is_file() or mark.read_text(encoding='ascii') != pack.sha:
                raise
            if key in COMPONENT_PACKS:
                from .desktop_runtimes import validate_payload
                validate_payload(key,target)
            elif key in BUILDER_PACKS:
                from .builder_resources import validate_payload
                validate_payload(key,target)
        return target


def _copy_verified_archive(source,archive,pack,progress,check):
    digest=hashlib.sha256();read=0
    with source.open('rb') as stream,archive.open('wb') as output:
        while chunk := stream.read(1024 * 1024):
            check()
            read += len(chunk)
            if read > pack.size:raise ValueError(E('E_MODEL_DOWNLOAD_SIZE'))
            digest.update(chunk);output.write(chunk)
            progress(M('Verifying installation file'), read * 100 // pack.size)
    if read != pack.size or digest.hexdigest() != pack.sha:raise ValueError(E('E_MODEL_CHECKSUM_FAILED'))
    progress(M('Installing verified files'), -1)


def _extract_archive(key,archive,payload,check):
    with ZipFile(archive) as z:
        if key == 'vfg':
            from .vfg_runtime import PINS
            members = {'nvvfx/libs/' + Path(name).name: name for name in PINS}
            members.update({name: 'licenses/' + Path(name).name for name in z.namelist()
                            if '.dist-info/licenses/' in name and not name.endswith('/')})
        else:members = {name: name for name in z.namelist()}
        for member, relative in members.items():
            dest = payload / relative
            if not dest.resolve().is_relative_to(payload.resolve()):raise ValueError(E('E_MODEL_ARCHIVE_PATH_INVALID'))
            dest.parent.mkdir(parents=True, exist_ok=True)
            with z.open(member) as src, dest.open('xb') as dst:
                while chunk := src.read(1024 * 1024):check();dst.write(chunk)
