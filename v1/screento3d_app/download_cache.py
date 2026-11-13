"""Pinned HTTPS downloads with bounded retries, resumable cache and process locks."""
from contextlib import contextmanager
import hashlib
import http.client
import os
from pathlib import Path
import re
import shutil
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, HTTPSHandler, HTTPRedirectHandler, build_opener

from .messages import ErrorMessage as E, Message as M
from .user_data import data_root


class SecureRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlsplit(newurl).scheme != 'https':
            raise ValueError(E('E_MODEL_TLS_INVALID'))
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_https(request):
    if urlsplit(request.full_url).scheme != 'https':
        raise ValueError(E('E_MODEL_TLS_INVALID'))
    response = build_opener(HTTPSHandler(), SecureRedirect()).open(request, timeout=30)
    if urlsplit(response.geturl()).scheme != 'https':
        response.close()
        raise ValueError(E('E_MODEL_TLS_INVALID'))
    return response


def cache_root():
    return data_root()/'downloads'


def check_cancel(cancelled):
    if cancelled():raise InterruptedError(E('E_INSTALL_CANCELLED'))


def wait_cancel(seconds, cancelled):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        check_cancel(cancelled)
        time.sleep(min(.1, max(0, deadline-time.monotonic())))


@contextmanager
def cache_lock(path, cancelled):
    # OS locks are released after a crash; no stale PID lock needs deleting.
    with path.open('a+b') as file:
        if file.seek(0,2)==0:file.write(b'0');file.flush()
        deadline=time.monotonic()+30
        while True:
            check_cancel(cancelled);file.seek(0)
            try:
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(file.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(file,fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic()>=deadline:raise RuntimeError(E('E_DOWNLOAD_BUSY')) from None
                wait_cancel(.1,cancelled)
        try:yield
        finally:
            file.seek(0)
            if os.name=='nt':msvcrt.locking(file.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(file,fcntl.LOCK_UN)


def verified(path, size, sha, cancelled):
    if path.is_symlink() or not path.is_file() or path.stat().st_size!=size:return False
    digest=hashlib.sha256()
    with path.open('rb') as file:
        while chunk:=file.read(4*1024*1024):
            check_cancel(cancelled);digest.update(chunk)
    return digest.hexdigest()==sha


def fetch(filename, url, size, sha, progress, cancelled, *, root=None, attempts=3):
    if (Path(filename).name!=filename or '/' in filename or '\\' in filename
            or not re.fullmatch('[0-9a-f]{64}',sha) or size<=0):
        raise ValueError('Invalid pinned download identity')
    if urlsplit(url).scheme!='https':raise ValueError(E('E_MODEL_TLS_INVALID'))
    directory=(Path(root) if root is not None else cache_root())/sha
    directory.mkdir(parents=True,exist_ok=True)
    target=directory/filename;partial=directory/(filename+'.part')
    if target.is_symlink() or partial.is_symlink():raise ValueError(E('E_MODEL_ARCHIVE_PATH_INVALID'))
    with cache_lock(directory/'download.lock',cancelled):
        if verified(target,size,sha,cancelled):
            progress(M('Using verified download cache'),100);return target
        # Only this pinned cache entry is removed; user-supplied files are untouched.
        target.unlink(missing_ok=True)
        for attempt in range(attempts):
            check_cancel(cancelled)
            offset=partial.stat().st_size if partial.exists() else 0
            if offset>size:partial.unlink();offset=0
            if offset==size:
                if verified(partial,size,sha,cancelled):partial.replace(target);return target
                partial.unlink();raise ValueError(E('E_MODEL_CHECKSUM_FAILED'))
            if shutil.disk_usage(directory).free<size-offset+16*1024**2:
                raise OSError(E('E_INSTALL_SPACE_REQUIRED',v0=(size-offset)/1e9))
            headers={'Accept-Encoding':'identity','User-Agent':'ScreenTo3D/1.0'}
            if offset:headers['Range']=f'bytes={offset}-'
            try:
                with open_https(Request(url,headers=headers)) as response:
                    status=response.status
                    if response.headers.get('Content-Encoding','identity')!='identity':
                        raise ValueError(E('E_DOWNLOAD_RANGE'))
                    if status==206:
                        match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',response.headers.get('Content-Range',''))
                        if not match or tuple(map(int,match.groups()))!=(offset,size-1,size):
                            raise ValueError(E('E_DOWNLOAD_RANGE'))
                    elif status==200:
                        offset=0  # A server ignoring Range must replace, never append.
                    else:raise ValueError(E('E_DOWNLOAD_RANGE'))
                    length=response.headers.get('Content-Length')
                    if length is not None and int(length)!=size-offset:
                        raise ValueError(E('E_MODEL_DOWNLOAD_SIZE'))
                    read=offset
                    with partial.open('ab' if offset else 'wb') as output:
                        while True:
                            check_cancel(cancelled)
                            chunk=response.read(min(1024*1024,size-read+1))
                            if not chunk:break
                            read+=len(chunk)
                            if read>size:raise ValueError(E('E_MODEL_DOWNLOAD_SIZE'))
                            output.write(chunk)
                            progress(M('Resuming download') if offset else M('Downloading files'),read*100//size)
                if read!=size:raise http.client.IncompleteRead(b'',size-read)
                if not verified(partial,size,sha,cancelled):
                    partial.unlink();raise ValueError(E('E_MODEL_CHECKSUM_FAILED'))
                partial.replace(target);return target
            except (HTTPError,URLError,TimeoutError,ConnectionError,http.client.IncompleteRead) as error:
                if isinstance(error,HTTPError) and error.code not in (408,429,500,502,503,504):raise
                if attempt+1==attempts:raise
                progress(M('Connection interrupted. Retrying download…'),-1)
                wait_cancel(min(2**attempt,4),cancelled)
        raise RuntimeError('Download retry limit reached')
