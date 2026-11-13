"""Package a prepared portable desktop as independent, bounded GitHub assets."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from zipfile import ZipFile,ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]
MAX_ASSET=1900*1024**2  # Below GitHub's 2 GiB per-asset limit, including ZIP records.


def digest(path):
    with path.open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()


def package(app,output,packs,runtime_packs=None):
    app=app.resolve();output=output.resolve()
    info=json.loads((app/'build-manifest.json').read_text(encoding='utf-8'))
    model_downloads=info.get('model_pack_downloads',{})
    if model_downloads and packs:
        raise ValueError('Publish model packs in their separate release; --packs is for legacy offline packages.')
    if model_downloads and (app/'packs').exists() and any((app/'packs').iterdir()):
        raise ValueError('A public-download application must not accidentally bundle model packs.')
    upstream_checks=[]
    model_checks=[]
    if info.get('upstream_downloads'):
        import sys
        sys.path.insert(0,str(ROOT/'v1'))
        from screento3d_app.upstream_check import check
        upstream=json.loads((app/'v1/screento3d_app/upstream_sources.json').read_text(encoding='utf-8'))
        upstream_checks=check(upstream['artifacts'],info['upstream_downloads'])
    if model_downloads:
        import sys
        sys.path.insert(0,str(ROOT/'v1'))
        from screento3d_app.upstream_check import check
        model_checks=check(model_downloads,model_downloads)
    version=info['product_version'];name=f'ScreenTo3D-{version}';app_root='ScreenTo3D'
    if app.name not in (name,app_root):raise ValueError('The portable folder must be named ScreenTo3D.')
    if output.exists():raise ValueError('Choose a new archive output directory.')
    import sys
    sys.path.insert(0,str(ROOT/'v1'))
    from screento3d_app.portable_package import exclusion
    files=sorted((p for p in app.rglob('*') if p.is_file() and not exclusion(p.relative_to(app))),
                 key=lambda p:(-p.stat().st_size,p.as_posix()))
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
            assets.append(dict(name=path.name,kind='application',root=app_root,bytes=path.stat().st_size,sha256=digest(path)))
            print('Archived',path.name,path.stat().st_size,flush=True)
        try:
            for index,path in enumerate(files):
                if archive is not None and archive.fp.tell()+path.stat().st_size+32*1024**2>MAX_ASSET:finish()
                if archive is None:
                    part+=1;archive=ZipFile(stage/f'{name}-windows-x64-part{part:02d}.zip','w',compression=ZIP_DEFLATED,compresslevel=6,allowZip64=True)
                archive.write(path,arcname=f'{app_root}/{path.relative_to(app).as_posix()}')
                if index%500==0:print('Packing',index+1,'/',len(files),flush=True)
            finish()
        finally:
            if archive is not None:archive.close()
        # Part numbers communicate a multi-archive set; omit them for one ZIP.
        if len(assets)==1:
            single=f'{name}-windows-x64.zip'
            (stage/assets[0]['name']).rename(stage/single)
            assets[0]['name']=single
        if packs and not info.get('bundled_model_packs'):
            import sys
            sys.path.insert(0,str(ROOT/'v1'))
            from screento3d_app.optional_models import PACKS
            path=stage/f'{name}-optional-models.zip'
            with ZipFile(path,'w',compression=ZIP_DEFLATED,compresslevel=6) as archive:
                for key in ('da2-base','vda-small'):
                    spec=PACKS[key];source=packs/spec.filename
                    if source.stat().st_size!=spec.size or digest(source)!=spec.sha:raise ValueError(f'Optional model pin mismatch: {key}')
                    archive.write(source,arcname='packs/'+spec.filename)
            assets.append(dict(name=path.name,kind='optional-models',root='packs',bytes=path.stat().st_size,sha256=digest(path)))
        if info.get('tensorrt_builder_resources')=='GPU-selected pinned sidecar packs':
            import sys
            sys.path.insert(0,str(ROOT/'v1'))
            from screento3d_app.builder_resources import PACKS as resources
            runtime_packs=Path(runtime_packs) if runtime_packs else app.parent/'runtime-packs'
            for resource in resources.values():
                source=runtime_packs/resource['filename']
                if source.stat().st_size!=resource['size'] or digest(source)!=resource['sha']:raise ValueError('GPU runtime pack pin mismatch')
                path=stage/source.name
                # Pinned sidecars are immutable; sharing local storage avoids
                # duplicating all alternative GPU resources during staging.
                try:os.link(source,path)
                except OSError:shutil.copy2(source,path)
                assets.append(dict(name=path.name,kind='gpu-runtime',root='runtime-packs',bytes=resource['size'],sha256=resource['sha']))
        if info.get('desktop_components')=='on-demand pinned packs':
            import sys
            sys.path.insert(0,str(ROOT/'v1'))
            from screento3d_app.desktop_runtimes import PACKS as components
            directory=Path(runtime_packs) if runtime_packs else app.parent/'runtime-packs'
            for item in components.values():
                source=directory/item['filename']
                if source.stat().st_size!=item['size'] or digest(source)!=item['sha']:raise ValueError('Component pack pin mismatch')
                try:os.link(source,stage/source.name)
                except OSError:shutil.copy2(source,stage/source.name)
                assets.append(dict(name=source.name,kind='component-runtime',root='runtime-packs',bytes=item['size'],sha256=item['sha']))
        manifest=dict(product='ScreenTo3D',product_version=version,source_commit=info['source_commit'],app_root=app_root,data_directory='data',
            app_bytes=sum(p.stat().st_size for p in files),app_files=len(files),assets=assets,upstream_download_checks=upstream_checks,model_download_checks=model_checks,
            extraction='Application root is ScreenTo3D. User data is never included. Close the app before replacing application files; keep data/. Optional packs are siblings of the app.')
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
    parser.add_argument('--runtime-packs',type=Path)
    args=parser.parse_args();package(args.app,args.output,args.packs,args.runtime_packs)
