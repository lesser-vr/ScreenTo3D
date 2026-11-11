"""Prepare the same-version full FFmpeg feature set without duplicated static tools."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from urllib.request import urlopen
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
URL='https://github.com/GyanD/codexffmpeg/releases/download/9.0.1/ffmpeg-9.0.1-full_build-shared.zip'
SIZE=97261187
SHA256='6fd54b3b4f49117a307877b570f5e1659090f178973298658b41f5c559b5b5ab'


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def prepare(output,archive=None):
    output=Path(output);archive=Path(archive) if archive else ROOT/'out/downloads/ffmpeg-9.0.1-full_build-shared.zip'
    archive.parent.mkdir(parents=True,exist_ok=True)
    if not archive.exists():
        with tempfile.TemporaryDirectory(dir=archive.parent) as scratch:
            partial=Path(scratch)/archive.name;count=0
            with urlopen(URL,timeout=30) as source,partial.open('wb') as destination:
                if not source.geturl().startswith('https://'):raise ValueError('FFmpeg download must retain HTTPS')
                while chunk:=source.read(1024*1024):
                    count+=len(chunk)
                    if count>SIZE:raise ValueError('FFmpeg archive exceeds its pinned size')
                    destination.write(chunk)
            if count!=SIZE or digest(partial)!=SHA256:raise ValueError('FFmpeg archive differs from publisher pin')
            partial.rename(archive)
    if archive.stat().st_size!=SIZE or digest(archive)!=SHA256:raise ValueError('FFmpeg archive differs from publisher pin')
    output.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(archive) as zip:
        selected={}
        for info in zip.infolist():
            parts=Path(info.filename).parts
            if len(parts)<2 or '..' in parts or info.is_dir():continue
            relative=Path(*parts[1:])
            if relative.parent==Path('bin') and (relative.suffix.lower()=='.dll' or relative.name in ('ffmpeg.exe','ffprobe.exe')):
                selected[relative.name]=info
            elif relative.parent==Path('.') and relative.name.lower().startswith(('license','copying','notice','readme')):
                selected['licenses/'+relative.name]=info
        if not {'ffmpeg.exe','ffprobe.exe'}<=set(selected):raise ValueError('Required FFmpeg tools missing')
        # Installed files are verified against the authenticated archive itself,
        # not a self-declared manifest next to user-editable executables.
        identities={name:dict(bytes=info.file_size,sha256=hashlib.sha256(zip.read(info)).hexdigest()) for name,info in selected.items()}
        if output.exists():
            actual={p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()}
            if actual!=set(identities)|{'provenance.json'}:raise ValueError('Prepared FFmpeg contains unexpected files')
            for name,pin in identities.items():
                path=output/name
                if not path.is_file() or path.stat().st_size!=pin['bytes'] or digest(path)!=pin['sha256']:raise ValueError('Prepared FFmpeg differs; choose a new output directory')
        else:
            with tempfile.TemporaryDirectory(dir=output.parent) as scratch:
                stage=Path(scratch)/'ffmpeg';stage.mkdir()
                for name,info in selected.items():
                    target=stage/name;target.parent.mkdir(parents=True,exist_ok=True)
                    with zip.open(info) as src,target.open('xb') as dst:shutil.copyfileobj(src,dst,1024*1024)
                (stage/'provenance.json').write_text(json.dumps(dict(version='9.0.1',variant='full shared',url=URL,archive_sha256=SHA256,files=identities),indent=2)+'\n',encoding='utf-8')
                stage.rename(output)
    return dict(version='9.0.1',variant='full shared',url=URL,archive_sha256=SHA256,bytes=sum(v['bytes'] for v in identities.values()))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path);parser.add_argument('--archive',type=Path)
    args=parser.parse_args();print(json.dumps(prepare(args.output,args.archive),indent=2))
