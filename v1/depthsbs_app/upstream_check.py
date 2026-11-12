"""Anonymous release-time availability checks for exact publisher archives."""
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request

from .download_cache import open_https


def probe(key,pin):
    with open_https(Request(pin['url'],headers={'Range':'bytes=0-31','Accept-Encoding':'identity'})) as response:
        if response.status==206:
            if response.headers.get('Content-Range')!=f"bytes 0-31/{pin['size']}":
                raise ValueError('Unexpected original archive range: '+key)
        elif response.status==200:
            if response.headers.get('Content-Length')!=str(pin['size']):
                raise ValueError('Unexpected original archive size: '+key)
        else:raise ValueError('Original archive is unavailable: '+key)
        if not response.read(32).startswith(b'PK\x03\x04'):
            raise ValueError('Original archive is not a ZIP: '+key)
        return dict(component=key,status=response.status,bytes=pin['size'],sha256=pin['sha256'],scope='anonymous header/prefix probe; full hash verified on download')


def check(catalog,keys):
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(probe,key,catalog[key]) for key in keys]
        return [future.result() for future in futures]
