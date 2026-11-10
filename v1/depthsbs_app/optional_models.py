"""Pinned optional downloads. Only a fully verified installation becomes visible."""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen
from zipfile import ZipFile

from .desktop_jobs import ROOT


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
                     '이 PC의 NVIDIA GPU에 맞춰 최적화 · CC BY-NC 4.0 비상업용'),
    'vda-small': Pack('VDA Small', 'vda-small-onnx-v3.zip', 363291834,
                      'b4e68c45328e37b601c95f1d06a024c41c510c6c980ba2fcdec5b1030603778f',
                      '이 PC의 NVIDIA GPU에 맞춰 최적화 · Apache 2.0'),
    'vfg': Pack('NVIDIA VFG', 'nvidia_vfx-0.2.0.0-cp311-cp311-win_amd64.whl', 435809365,
                '5aaf6a42bc6b6dbbf52fcb714194c994a6893cbbf7ada38bc2165a1f83e4a6fc',
                'NVIDIA VFX · NVIDIA 소프트웨어 및 모델 약관 적용'),
}


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


def model_root(key):
    local = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local'))
    return local / 'DepthSBS' / 'models' / key / PACKS[key].sha[:16]


def installed_path(key):
    from .engine_cache import device_identity, device_key
    root = model_root(key)
    return root / device_key(device_identity()) if key in GRAPH_HASHES else root


def available(key, directory):
    """Cheap inventory only. Workers still validate the actual artifact on use."""
    if key not in PACKS or not directory:
        return False
    path = Path(directory)
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
    # A distributor supplies the origin together with the desktop build. The
    # origin cannot change the digest or the engine version the app accepts.
    origin = ROOT / 'model-origin.txt'
    if origin.is_file():
        base = origin.read_text(encoding='utf-8').strip().rstrip('/')
        if urlsplit(base).scheme != 'https' or not urlsplit(base).hostname:
            raise ValueError('모델 배포 주소를 확인하세요. HTTPS 주소가 필요합니다.')
        return base + '/' + pack.filename
    for folder in (ROOT.parent / 'packs', ROOT / 'out/desktop-distribution/packs'):
        if (folder / pack.filename).is_file():
            return folder / pack.filename
    raise FileNotFoundError('이 배포본에 모델 서버가 지정되지 않았습니다. 배포자가 제공한 모델 팩을 선택하세요.')


def optimize(key, payload, cancelled):
    error = payload.parent/'build-error.txt'
    cmd = [sys.executable, '-m', 'depthsbs_app.build_local_engine', key, str(payload), str(error)]
    with subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL) as child:
        try:
            while child.poll() is None:
                if cancelled():
                    raise InterruptedError('설치를 취소했습니다.')
                try:
                    child.wait(timeout=0.2)
                except subprocess.TimeoutExpired:
                    continue
            if child.returncode:
                reason = error.read_text(encoding='utf-8') if error.is_file() else f'종료 코드 {child.returncode}'
                raise RuntimeError('GPU 엔진 최적화 실패 · ' + reason)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()


def install(key, source, target, progress, cancelled):
    pack = PACKS[key]
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    def check():
        if cancelled():
            raise InterruptedError('설치를 취소했습니다.')

    with tempfile.TemporaryDirectory(prefix='.install-', dir=target.parent) as scratch:
        archive = Path(scratch) / pack.filename
        payload = Path(scratch) / 'ready'
        payload.mkdir()
        digest = hashlib.sha256()
        read = 0
        required = pack.size * (4 if key in GRAPH_HASHES else 2)
        if shutil.disk_usage(scratch).free < required:
            raise OSError(f'설치에 약 {required / 1e9:.1f} GB의 여유 공간이 필요합니다.')
        check()
        with (source.open('rb') if isinstance(source, Path) else urlopen(source, timeout=12)) as stream:
            if not isinstance(source, Path) and urlsplit(stream.geturl()).scheme != 'https':
                raise ValueError('모델 서버의 보안 연결을 확인하세요.')
            with archive.open('wb') as output:
                while chunk := stream.read(1024 * 1024):
                    check()
                    read += len(chunk)
                    if read > pack.size:
                        raise ValueError('다운로드 용량이 배포 기록과 다릅니다.')
                    digest.update(chunk)
                    output.write(chunk)
                    progress('파일 받는 중', read * 100 // pack.size)
        if read != pack.size or digest.hexdigest() != pack.sha:
            raise ValueError('파일 검증에 실패했습니다. 모델 팩을 다시 받으세요.')
        progress('검증된 파일 설치 중', -1)
        with ZipFile(archive) as z:
            if key == 'vfg':
                from .vfg_runtime import PINS
                members = {'nvvfx/libs/' + Path(name).name: name for name in PINS}
                members.update({name: 'licenses/' + Path(name).name for name in z.namelist()
                                if '.dist-info/licenses/' in name and not name.endswith('/')})
            else:
                members = {name: name for name in z.namelist()}
            for member, relative in members.items():
                dest = payload / relative
                if not dest.resolve().is_relative_to(payload.resolve()):
                    raise ValueError('잘못된 모델 파일 경로입니다.')
                dest.parent.mkdir(parents=True, exist_ok=True)
                with z.open(member) as src, dest.open('xb') as dst:
                    while chunk := src.read(1024 * 1024):
                        check()
                        dst.write(chunk)
        if key == 'vfg':
            (payload/'licenses/NOTICE.txt').write_text(
                'Licensed by NVIDIA Corporation under the NVIDIA Open Model License\n', encoding='utf-8')
        else:
            check()
            progress('이 GPU에 맞게 엔진 최적화 및 검증 중…', -1)
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
        return target
