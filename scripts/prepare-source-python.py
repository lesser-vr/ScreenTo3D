"""Use the same pinned, unpackaged CPython for native source-checkout launches."""
import hashlib
import importlib.util
from pathlib import Path
import shutil
import sys
import tempfile
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]


def prepare(archive,destination=None):
    spec=importlib.util.spec_from_file_location('desktop_python_pin',ROOT/'scripts/build-desktop-portable.py')
    builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
    archive=Path(archive);destination=destination or ROOT/'out/desktop-python'
    with archive.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=builder.PYTHON_SHA:raise ValueError('Untrusted source Python ZIP')
    with ZipFile(archive) as zip:
        if destination.exists():
            if not all((destination/name).is_file() and hashlib.sha256((destination/name).read_bytes()).digest()==hashlib.sha256(zip.read(name)).digest()
                       for name in ('python.exe','pythonw.exe','python313.dll','python313.zip')):
                raise ValueError('Existing source interpreter differs from the pinned runtime; preserve it and choose a new destination')
        else:
            destination.parent.mkdir(parents=True,exist_ok=True)
            with tempfile.TemporaryDirectory(dir=destination.parent) as scratch:
                stage=Path(scratch)/'python';zip.extractall(stage);stage.rename(destination)
    text='python313.zip\n.\n../../v1\n../gui-python-deps\n../capture-python-deps\n../v1-python-deps\n../iw3-compile-deps-20261105\n../vda-oracle-env/Lib/site-packages\nimport site\n'
    if not (destination/'python313._pth').exists() or (destination/'python313._pth').read_text()!=text:
        (destination/'python313._pth').write_text(text,encoding='ascii')
    return destination


if __name__=='__main__':print(prepare(Path(sys.argv[1])))
