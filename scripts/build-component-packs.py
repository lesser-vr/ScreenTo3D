"""Build pinned first-use desktop components from reviewed local distributions."""
import argparse,hashlib,json,shutil,sys,tempfile
from pathlib import Path
from zipfile import ZipFile,ZipInfo,ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'v1'))
from screento3d_app.desktop_runtimes import PACKS
from screento3d_app.builder_resources import LAYOUT


def digest(path):
    with Path(path).open('rb') as file:return hashlib.file_digest(file,'sha256').hexdigest()


def build(output,media=None,cuda_runtime=None):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    bundle=ROOT/'out/gpu-preview/ScreenTo3D-GPU-Preview'
    media=Path(media) if media else ROOT/'out/ffmpeg-shared-9.0.1'
    cuda_runtime=Path(cuda_runtime) if cuda_runtime else Path('C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v13.1/bin/x64/cudart64_13.dll')
    for key,pack in PACKS.items():
        final=output/pack['filename']
        if final.exists():
            if final.stat().st_size!=pack['size'] or digest(final)!=pack['sha']:raise ValueError('Existing component pack differs from trusted pin')
            continue
        with tempfile.TemporaryDirectory(dir=output) as scratch:
            scratch=Path(scratch);layout=scratch/'builder-layout.json';layout.write_text(json.dumps(LAYOUT),encoding='utf-8')
            files={}
            for name,pin in pack['files'].items():
                if key=='media-tools':source=media/name
                elif name=='builder-layout.json':source=layout
                elif name=='cudart64_13.dll':source=cuda_runtime
                elif name.startswith('licenses/'):source=bundle/Path(name).name
                else:source=bundle/'_internal/runtime'/name
                if source.stat().st_size!=pin['bytes'] or digest(source)!=pin['sha256']:raise ValueError('Component input differs from trusted pin: '+name)
                files[name]=source
            archive=scratch/pack['filename']
            with ZipFile(archive,'w',compression=ZIP_DEFLATED,compresslevel=6) as zip:
                for name,path in sorted(files.items()):
                    info=ZipInfo(name,(1980,1,1,0,0,0));info.create_system=0;info.external_attr=0x20
                    info.compress_type=ZIP_DEFLATED;info._compresslevel=6
                    with path.open('rb') as src,zip.open(info,'w',force_zip64=True) as dst:shutil.copyfileobj(src,dst,1024*1024)
            if archive.stat().st_size!=pack['size'] or digest(archive)!=pack['sha']:raise ValueError('Component archive differs from trusted pin: '+key)
            archive.rename(final)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
    args=parser.parse_args();build(args.output)
