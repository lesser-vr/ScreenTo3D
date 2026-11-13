"""Explicit, cancelable copy/verify import. Cleanup is limited to verified files."""
import hashlib
import os
from pathlib import Path
import shutil
import tempfile

from .messages import ErrorMessage as E
from .user_data import data_root,data_lock,legacy_roots,_check


def _destination(relative):
    parts=relative.parts
    if not parts:return None
    if parts[0]=='models' and len(parts)>1:
        from .optional_models import GRAPH_HASHES,PACKS
        runtime=parts[1] in PACKS and parts[1] not in GRAPH_HASHES
        return Path('runtimes' if runtime else 'models',*parts[1:])
    if parts[0] in ('downloads','engines'):return Path('cache',*parts)
    return None


def inventory(sources=None):
    """Metadata only; no GPU, registry access, copying or source mutation."""
    root=data_root();items=[];seen=set()
    for source in legacy_roots() if sources is None else sources:
        source=Path(source);_check(source,source.parent)
        if not source.is_dir():continue
        source=source.resolve()
        if root.resolve().is_relative_to(source) or source.is_relative_to(root.resolve()):
            raise OSError(E('E_DATA_IMPORT_SOURCE'))
        for category in ('models','downloads','engines'):
            folder=source/category;_check(folder,source)
            if not folder.exists():continue
            for path in _files(folder,source):
                if not path.is_file():continue
                relative=_destination(path.relative_to(source))
                if relative is None or relative.as_posix() in seen:continue
                seen.add(relative.as_posix());stat=path.stat()
                items.append(dict(source=source,path=path,relative=relative,bytes=stat.st_size,mtime=stat.st_mtime_ns))
                if len(items)>100000:raise OSError(E('E_DATA_IMPORT_LIMIT'))
    return items


def _files(folder,root,depth=0):
    if depth>32:raise OSError(E('E_DATA_IMPORT_LIMIT'))
    for path in folder.iterdir():
        _check(path,root)
        if path.is_dir():yield from _files(path,root,depth+1)
        else:yield path


def _hash(path,cancelled):
    _cancel(cancelled)
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        while chunk:=stream.read(1024*1024):
            _cancel(cancelled);digest.update(chunk)
    return digest.hexdigest()


def _cancel(cancelled):
    if cancelled():raise InterruptedError(E('E_DATA_IMPORT_CANCELLED'))


def import_files(items,progress=lambda done,total:None,cancelled=lambda:False,*,cleanup=False):
    root=data_root();total=sum(item['bytes'] for item in items);done=0
    copied=[];conflicts=0;removed=0
    with data_lock():
        needed=sum(item['bytes'] for item in items if not (root/item['relative']).exists())
        if shutil.disk_usage(root).free<needed+16*1024**2:raise OSError(E('E_DATA_IMPORT_SPACE'))
        for item in items:
            _cancel(cancelled);source=item['path'];base=item['source'];target=root/item['relative']
            _check(base,base.parent);_check(root,root.parent)
            _check(source,base);_check(target,root)
            before=source.stat()
            if (before.st_size,before.st_mtime_ns)!=(item['bytes'],item['mtime']):raise OSError(E('E_DATA_IMPORT_CHANGED'))
            # Validate every destination ancestor before opening a stage file.
            for parent in target.parents:
                if parent==root:break
                _check(parent,root)
            target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists():
                source_sha=_hash(source,cancelled)
                after=source.stat()
                if (after.st_size,after.st_mtime_ns)!=(item['bytes'],item['mtime']):raise OSError(E('E_DATA_IMPORT_CHANGED'))
                if _hash(target,cancelled)==source_sha:copied.append((item,target,source_sha))
                else:conflicts+=1
                done+=item['bytes'];progress(done,total);continue
            stage=None
            try:
                with tempfile.NamedTemporaryFile(prefix='.import-',dir=target.parent,delete=False) as output:
                    stage=Path(output.name);digest=hashlib.sha256();count=0
                    with source.open('rb') as stream:
                        while chunk:=stream.read(1024*1024):
                            _cancel(cancelled);count+=len(chunk)
                            if count>item['bytes']:raise OSError(E('E_DATA_IMPORT_CHANGED'))
                            digest.update(chunk);output.write(chunk);done+=len(chunk);progress(done,total)
                    output.flush();os.fsync(output.fileno())
                after=source.stat()
                if count!=item['bytes'] or (after.st_size,after.st_mtime_ns)!=(item['bytes'],item['mtime']):
                    raise OSError(E('E_DATA_IMPORT_CHANGED'))
                sha=digest.hexdigest()
                if _hash(stage,cancelled)!=sha:raise OSError(E('E_DATA_IMPORT_VERIFY'))
                after=source.stat()
                if (after.st_size,after.st_mtime_ns)!=(item['bytes'],item['mtime']):raise OSError(E('E_DATA_IMPORT_CHANGED'))
                _cancel(cancelled);_check(target,root)
                if target.exists():
                    if _hash(target,cancelled)!=sha:conflicts+=1;continue
                else:stage.rename(target)
                copied.append((item,target,sha))
            finally:
                if stage is not None and stage.exists():stage.unlink()
        # No source deletion until the entire copy/verification stage succeeds.
        if cleanup:
            empty_dirs=set()
            for item,target,sha in copied:
                _cancel(cancelled);source=item['path'];_check(source,item['source']);_check(target,root)
                _check(item['source'],item['source'].parent);_check(root,root.parent)
                try:
                    source_sha=_hash(source,cancelled);target_sha=_hash(target,cancelled);stat=source.stat()
                    if source_sha==target_sha==sha and (stat.st_size,stat.st_mtime_ns)==(item['bytes'],item['mtime']):
                        source.unlink();removed+=1
                        for parent in source.parents:
                            if parent==item['source']:break
                            empty_dirs.add((parent,item['source']))
                except InterruptedError:raise
                except OSError:pass
            # Only empty owned subfolders, never recursively delete a legacy root.
            for path,base in sorted(empty_dirs,key=lambda pair:len(pair[0].parts),reverse=True):
                try:_check(path,base);path.rmdir()
                except OSError:pass
        _cancel(cancelled)
        return dict(files=len(copied),bytes=sum(item['bytes'] for item,_,_ in copied),
                    conflicts=conflicts,removed=removed,preserved=len(items)-removed)
