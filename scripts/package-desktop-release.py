"""Package a prepared portable desktop as independent, bounded GitHub assets."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from zipfile import ZipFile,ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]
MAX_ASSET=1900*1024**2  # Below GitHub's 2 GiB per-asset limit, including ZIP records.


def digest(path):
    with path.open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()


def package(app,output,packs):
    app=app.resolve();output=output.resolve()
    info=json.loads((app/'build-manifest.json').read_text(encoding='utf-8'))
    version=info['product_version'];name=f'ScreenTo3D-{version}'
    if app.name!=name:raise ValueError(f'The portable folder must be named {name}.')
    if output.exists():raise ValueError('Choose a new archive output directory.')
    files=sorted((p for p in app.rglob('*') if p.is_file()),key=lambda p:(-p.stat().st_size,p.as_posix()))
    if not files or any(p.is_symlink() or p.stat().st_size>=MAX_ASSET-32*1024**2 for p in files):
        raise ValueError('Cannot safely package an empty, linked or oversized portable tree.')
    output.parent.mkdir(parents=True,exist_ok=True)
    assets=[]
    with tempfile.TemporaryDirectory(dir=output.parent) as scratch:
        stage=Path(scratch)/'assets';stage.mkdir()
        archive=None;part=0
        def finish():
            nonlocal archive
            if archive is None:return
            path=Path(archive.filename);archive.close();archive=None
            assert path.stat().st_size<2*1024**3
            assets.append(dict(name=path.name,kind='application',root=name,bytes=path.stat().st_size,sha256=digest(path)))
            print('Archived',path.name,path.stat().st_size,flush=True)
        try:
            for index,path in enumerate(files):
                if archive is not None and archive.fp.tell()+path.stat().st_size+32*1024**2>MAX_ASSET:finish()
                if archive is None:
                    part+=1;archive=ZipFile(stage/f'{name}-windows-x64-part{part:02d}.zip','w',compression=ZIP_DEFLATED,compresslevel=6,allowZip64=True)
                archive.write(path,arcname=f'{name}/{path.relative_to(app).as_posix()}')
                if index%500==0:print('Packing',index+1,'/',len(files),flush=True)
            finish()
        finally:
            if archive is not None:archive.close()
        if packs:
            import sys
            sys.path.insert(0,str(ROOT/'v1'))
            from depthsbs_app.optional_models import PACKS
            path=stage/f'{name}-optional-models.zip'
            with ZipFile(path,'w',compression=ZIP_DEFLATED,compresslevel=6) as archive:
                for key in ('da2-base','vda-small'):
                    spec=PACKS[key];source=packs/spec.filename
                    if source.stat().st_size!=spec.size or digest(source)!=spec.sha:raise ValueError(f'Optional model pin mismatch: {key}')
                    archive.write(source,arcname='packs/'+spec.filename)
            assets.append(dict(name=path.name,kind='optional-models',root='packs',bytes=path.stat().st_size,sha256=digest(path)))
        manifest=dict(product='ScreenTo3D',product_version=version,source_commit=info['source_commit'],
            app_bytes=sum(p.stat().st_size for p in files),app_files=len(files),assets=assets,
            extraction='All application ZIPs have disjoint entries; extract into the same new directory. Optional packs are siblings of the app.')
        (stage/'release-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
        for file in ('Extract-ScreenTo3D.cmd','Extract-ScreenTo3D.ps1'):
            shutil.copy2(ROOT/'distribution'/file,stage/file)
        (stage/'SHA256SUMS.txt').write_text(''.join(f'{digest(p)}  {p.name}\n' for p in sorted(stage.iterdir()) if p.is_file()),encoding='ascii')
        stage.rename(output)
    print(json.dumps(manifest,indent=2),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('app',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--packs',type=Path)
    args=parser.parse_args();package(args.app,args.output,args.packs)
