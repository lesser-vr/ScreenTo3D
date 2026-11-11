"""Build deterministic, pinned TensorRT resource sidecars from the reviewed SDK."""
import argparse
import hashlib
from pathlib import Path
import shutil
import sys
import tempfile
from zipfile import ZipFile,ZipInfo,ZIP_STORED

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'v1'))
from depthsbs_app.builder_resources import PACKS,verify


def digest(path):
    with path.open('rb') as file:return hashlib.file_digest(file,'sha256').hexdigest()


def build(output,runtime=None,license=None):
    base=ROOT/'out/gpu-preview/DepthSBS-GPU-Preview'
    runtime=Path(runtime) if runtime else base/'_internal/runtime'
    license=Path(license) if license else base/'TENSORRT-LICENSE.txt'
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    for key,pack in PACKS.items():
        files={name:(license if name=='TENSORRT-LICENSE.txt' else runtime/name) for name in pack['files']}
        for name,path in files.items():
            pin=pack['files'][name]
            if path.stat().st_size!=pin['bytes'] or digest(path)!=pin['sha256']:raise ValueError(f'TensorRT source differs from release pin: {name}')
        final=output/pack['filename']
        if final.is_file() and final.stat().st_size==pack['size'] and digest(final)==pack['sha']:continue
        if final.exists():raise ValueError('Existing runtime pack differs; choose a new output directory.')
        with tempfile.TemporaryDirectory(dir=output) as scratch:
            archive=Path(scratch)/pack['filename']
            with ZipFile(archive,'w',compression=ZIP_STORED) as zip:
                for name,path in sorted(files.items()):
                    info=ZipInfo(name,(1980,1,1,0,0,0));info.create_system=0;info.external_attr=0x20
                    with path.open('rb') as src,zip.open(info,'w',force_zip64=True) as dst:shutil.copyfileobj(src,dst,1024*1024)
            if archive.stat().st_size!=pack['size'] or digest(archive)!=pack['sha']:raise ValueError(f'Runtime archive differs from pin: {key}')
            archive.rename(final)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
    args=parser.parse_args();build(args.output)
