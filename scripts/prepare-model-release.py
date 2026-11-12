"""Stage only pinned public model packs and their reviewed documentation."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'v1'))
from depthsbs_app.optional_models import GRAPH_HASHES,PACKS,MODEL_RELEASE,MODEL_REPOSITORY,model_downloads


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def prepare(output,packs,documents=ROOT/'distribution/models'):
    output=Path(output).resolve();packs=Path(packs);documents=Path(documents)
    if output.exists():raise ValueError('Choose a new model release directory.')
    provenance=json.loads((documents/'provenance.json').read_text(encoding='utf-8'))
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as scratch:
        stage=Path(scratch)/'release';stage.mkdir()
        public_files=['README.md','cards/da2-base.md','cards/vda-small.md',
                      'licenses/CC-BY-NC-4.0.txt','licenses/VDA-Apache-2.0.txt']
        for name in public_files:
            source=documents/name
            if source.is_symlink():raise ValueError('Public documentation cannot be a symlink.')
            target=stage/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        manifest=dict(schema=1,repository=MODEL_REPOSITORY,release=MODEL_RELEASE,
            artifact_scope='Converted ONNX graphs and numeric reference samples; no app, runtime, video or serialized engine',
            conversion_source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            conversion_source_dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True)),
            conversion_scripts={name:digest(ROOT/name) for name in
                ('scripts/build-model-packs.py','v1/base_trt_fp16_trial.py','v1/export_vda_spike.py','v1/build_vda_mixed_fp16.py','v1/build_vda_spatial_trial.py')},
            validated_environment=dict(os='Windows x64',gpu='RTX 5090',tensorrt='11.2.1.2',scope='Local validation; not certification of all GPUs'),
            models={})
        downloads=model_downloads()
        for key in GRAPH_HASHES:
            pack=PACKS[key];source=packs/pack.filename
            if source.is_symlink() or source.stat().st_size!=pack.size or digest(source)!=pack.sha:
                raise ValueError('Public pack differs from trusted pin: '+key)
            records={}
            with ZipFile(source) as archive:
                expected={f'518x{width}-fp16/{name}.onnx':sha for width,stages in GRAPH_HASHES[key].items() for name,sha in stages.items()}
                refs={f'518x{width}-fp16/reference.npz' for width in GRAPH_HASHES[key]}
                allowed=set(expected)|refs|{'NOTICE.txt'}|({'LICENSE.txt'} if key=='vda-small' else set())
                if set(archive.namelist())!=allowed or len(archive.namelist())!=len(allowed):
                    raise ValueError('Unexpected public pack members: '+key)
                for member in archive.infolist():
                    with archive.open(member) as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
                    if member.filename in expected and expected[member.filename]!=sha:
                        raise ValueError('Public graph differs from trusted pin: '+member.filename)
                    records[member.filename]=dict(bytes=member.file_size,sha256=sha)
            shutil.copyfile(source,stage/pack.filename)
            manifest['models'][key]=dict(filename=pack.filename,**downloads[key],**provenance[key],
                profiles=[dict(height=518,width=width) for width in GRAPH_HASHES[key]],members=records)
        (stage/'model-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
        files=sorted(p for p in stage.rglob('*') if p.is_file())
        (stage/'SHA256SUMS.txt').write_text(''.join(f'{digest(p)}  {p.relative_to(stage).as_posix()}\n' for p in files),encoding='ascii')
        stage.rename(output)
    print(json.dumps(dict(repository=MODEL_REPOSITORY,release=MODEL_RELEASE,output=str(output),models=list(manifest['models'])),indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
    parser.add_argument('--packs',type=Path,default=ROOT/'out/desktop-distribution/packs')
    args=parser.parse_args();prepare(args.output,args.packs)
