"""Original publisher archives -> existing pinned component payloads."""
from dataclasses import dataclass
import hashlib
import json
import shutil
from pathlib import Path
from zipfile import ZipFile

from . import download_cache
from .messages import ErrorMessage as E, Message as M

CATALOG=json.loads(Path(__file__).with_name('upstream_sources.json').read_text(encoding='utf-8'))
if CATALOG['schema']!=1:raise ValueError('Invalid upstream download catalog')
ARTIFACTS=CATALOG['artifacts']


@dataclass(frozen=True)
class OfficialSource:
    key: str

    @property
    def artifacts(self):
        return ('tensorrt','cuda') if self.key=='trt-core' else ('ffmpeg',) if self.key=='media-tools' else ('tensorrt',)

    @property
    def size(self):return sum(ARTIFACTS[key]['size'] for key in self.artifacts)

    @property
    def cached(self):
        return all((download_cache.cache_root()/ARTIFACTS[key]['sha256']/ARTIFACTS[key]['filename']).is_file()
                   for key in self.artifacts)


def fetch_artifact(key,progress,cancelled,*,root=None):
    pin=ARTIFACTS[key]
    return download_cache.fetch(pin['filename'],pin['url'],pin['size'],pin['sha256'],progress,cancelled,root=root)


def _copy_member(archive,member,target,pin,cancelled):
    if archive.getinfo(member).file_size!=pin['bytes']:raise ValueError(E('E_COMPONENT_INTEGRITY'))
    target.parent.mkdir(parents=True,exist_ok=True)
    digest=hashlib.sha256();read=0
    with archive.open(member) as source,target.open('xb') as output:
        while chunk:=source.read(1024*1024):
            download_cache.check_cancel(cancelled);read+=len(chunk)
            if read>pin['bytes']:raise ValueError(E('E_COMPONENT_INTEGRITY'))
            digest.update(chunk);output.write(chunk)
    if read!=pin['bytes'] or digest.hexdigest()!=pin.get('upstream_sha256',pin['sha256']):
        raise ValueError(E('E_COMPONENT_INTEGRITY'))


def _named_member(archive,name):
    matches=[info.filename for info in archive.infolist() if not info.is_dir() and Path(info.filename).name==name]
    if len(matches)!=1:raise ValueError(E('E_COMPONENT_INTEGRITY'))
    return matches[0]


def populate(source,payload,progress,cancelled):
    from .desktop_jobs import ROOT,BUNDLE
    from .desktop_runtimes import PACKS as components
    from .builder_resources import PACKS as builders,LAYOUT
    key=source.key
    expected=(components if key in components else builders)[key]['files']
    paths={name:fetch_artifact(name,progress,cancelled) for name in source.artifacts}
    required=sum(pin['bytes'] for pin in expected.values())+16*1024**2
    if shutil.disk_usage(payload).free<required:
        raise OSError(E('E_INSTALL_SPACE_REQUIRED',v0=required/1e9))
    progress(M('Installing verified files'),-1)
    if key=='media-tools':
        with ZipFile(paths['ffmpeg']) as archive:
            for name,pin in expected.items():
                if name=='provenance.json':continue
                _copy_member(archive,_named_member(archive,Path(name).name),payload/name,pin,cancelled)
        identities={name:pin for name,pin in expected.items() if name!='provenance.json'}
        provenance=dict(version=ARTIFACTS['ffmpeg']['version'],variant='full shared',
                        url=ARTIFACTS['ffmpeg']['url'],archive_sha256=ARTIFACTS['ffmpeg']['sha256'],files=identities)
        # Preserve publisher member order used by the original provenance builder.
        with ZipFile(paths['ffmpeg']) as archive:
            ordered={}
            for info in archive.infolist():
                basename=Path(info.filename).name
                name=next((name for name in identities if Path(name).name==basename),None)
                if name is not None and not info.is_dir():ordered[name]=identities[name]
        provenance['files']=ordered
        (payload/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n',encoding='utf-8')
        return
    with ZipFile(paths['tensorrt']) as trt:
        for name,pin in expected.items():
            target=payload/name
            if name=='builder-layout.json':
                target.write_text(json.dumps(LAYOUT),encoding='utf-8')
            elif name=='cudart64_13.dll':
                with ZipFile(paths['cuda']) as cuda:
                    _copy_member(cuda,_named_member(cuda,Path(name).name),target,pin,cancelled)
            elif name.endswith(('TENSORRT-LICENSE.txt','CUDA-EULA.txt')):
                # These notices are already bundled and independently pinned.
                notice=ROOT/'licenses'/Path(name).name
                if not notice.is_file():notice=BUNDLE.parent/Path(name).name
                data=notice.read_bytes()
                if len(data)!=pin['bytes'] or hashlib.sha256(data).hexdigest()!=pin['sha256']:
                    raise ValueError(E('E_COMPONENT_INTEGRITY'))
                target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
            else:_copy_member(trt,_named_member(trt,Path(name).name),target,pin,cancelled)
