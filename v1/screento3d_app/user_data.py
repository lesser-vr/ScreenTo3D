"""App-relative portable paths. Discovery never writes or imports user data."""
import os
from pathlib import Path
import sys
import tempfile

from .messages import ErrorMessage as E

APP_ROOT=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[2]


def data_root():return APP_ROOT/'data'


def settings_file():return data_root()/'settings.ini'


def _check(path,root):
    path=Path(path).absolute();root=Path(root).absolute()
    for candidate in (path,*path.parents):
        if candidate.is_symlink() or (hasattr(candidate,'is_junction') and candidate.is_junction()):
            raise OSError(E('E_PORTABLE_PATH'))
        if candidate==root:break
    else:raise OSError(E('E_PORTABLE_PATH'))
    if not path.resolve().is_relative_to(root.resolve()):raise OSError(E('E_PORTABLE_PATH'))


def prepare_environment():
    """Called before Qt/CUDA initialization; never silently use AppData instead."""
    root=data_root()
    try:
        _check(root,APP_ROOT);root.mkdir(exist_ok=True)
        for relative in ('models','runtimes','cache','cache/downloads','cache/engines',
                         'cache/qml','cache/qt','cache/cuda','cache/torch','cache/torch-extensions',
                         'cache/torchinductor','cache/triton','logs','temp'):
            path=root/relative;_check(path,root);path.mkdir(exist_ok=True)
        with tempfile.TemporaryFile(dir=root):pass
    except OSError as error:
        if error.args and isinstance(error.args[0],E):raise
        raise OSError(E('E_PORTABLE_WRITE')) from None
    for key,relative in {'QML_DISK_CACHE_PATH':'cache/qml',
                         'QSG_RHI_PIPELINE_CACHE_LOAD':'cache/qt/pipeline.cache',
                         'QSG_RHI_PIPELINE_CACHE_SAVE':'cache/qt/pipeline.cache',
                         'CUDA_CACHE_PATH':'cache/cuda','TORCH_HOME':'cache/torch',
                         'TORCH_EXTENSIONS_DIR':'cache/torch-extensions',
                         'TORCHINDUCTOR_CACHE_DIR':'cache/torchinductor','TRITON_CACHE_DIR':'cache/triton',
                         'TMP':'temp','TEMP':'temp'}.items():
        os.environ[key]=str(root/relative)
    sys.dont_write_bytecode=True;os.environ['PYTHONDONTWRITEBYTECODE']='1'
    tempfile.tempdir=str(root/'temp')
    return root
