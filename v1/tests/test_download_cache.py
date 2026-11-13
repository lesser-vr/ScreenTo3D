import hashlib
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from urllib.error import HTTPError
from urllib.request import Request

from screento3d_app import download_cache as cache
from screento3d_app import upstream_check


class Response(BytesIO):
    def __init__(self,data,*,status=200,start=0,total=None,interrupt=False):
        super().__init__(data);self.status=status;self.interrupt=interrupt;self.calls=0
        self.headers={'Content-Length':str(len(data))}
        if status==206:self.headers['Content-Range']=f'bytes {start}-{start+len(data)-1}/{total}'
    def geturl(self):return 'https://publisher.example/archive.zip'
    def read(self,size=-1):
        self.calls+=1
        if self.interrupt:
            if self.calls>1:raise TimeoutError('Injected interruption')
            size=2
        return super().read(size)


class DownloadCacheTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.data=b'PK\x03\x04owned-pinned-content';self.sha=hashlib.sha256(self.data).hexdigest()
        self.enterContext(patch.object(cache,'wait_cancel'))
        self.progress=Mock()

    def fetch(self,cancelled=lambda:False):
        return cache.fetch('owned.zip','https://publisher.example/archive.zip',len(self.data),self.sha,
                           self.progress,cancelled,root=self.root)

    @property
    def partial(self):return self.root/self.sha/'owned.zip.part'

    def seed(self,data):
        self.partial.parent.mkdir(parents=True,exist_ok=True);self.partial.write_bytes(data)

    def test_verified_cache_reuses_without_network_and_corrupt_cache_is_replaced(self):
        with patch.object(cache,'open_https',return_value=Response(self.data)) as opened:
            path=self.fetch();self.assertEqual(path.read_bytes(),self.data)
            self.assertIsNone(opened.call_args.args[0].get_header('Authorization'))
        with patch.object(cache,'open_https',side_effect=AssertionError('Cached download must not use network')):
            self.assertEqual(self.fetch(),path)
        path.write_bytes(b'x'*len(self.data))
        with patch.object(cache,'open_https',return_value=Response(self.data)) as opened:
            self.assertEqual(self.fetch().read_bytes(),self.data);opened.assert_called_once()

    def test_interrupted_connection_resumes_exact_offset_and_verifies_whole_file(self):
        responses=[Response(self.data,interrupt=True),Response(self.data[2:],status=206,start=2,total=len(self.data))]
        with patch.object(cache,'open_https',side_effect=responses) as opened:
            self.assertEqual(self.fetch().read_bytes(),self.data)
            self.assertEqual(opened.call_args_list[1].args[0].get_header('Range'),'bytes=2-')
            self.assertEqual(opened.call_count,2)
        self.assertFalse(self.partial.exists())

    def test_cancel_preserves_partial_and_next_request_resumes(self):
        cancelled=False
        def progress(*_):
            nonlocal cancelled
            cancelled=True
        with patch.object(cache,'open_https',return_value=Response(self.data)),patch.object(self,'progress',side_effect=progress):
            with self.assertRaises(InterruptedError):self.fetch(lambda:cancelled)
        # Even a complete-size partial must be hash-verified before it becomes cache.
        self.assertEqual(self.partial.read_bytes(),self.data)
        with patch.object(cache,'open_https',side_effect=AssertionError('Completed partial needs no new request')):
            self.assertEqual(self.fetch().read_bytes(),self.data)

    def test_server_ignoring_range_restarts_without_appending(self):
        self.seed(self.data[:4])
        with patch.object(cache,'open_https',return_value=Response(self.data)):
            self.assertEqual(self.fetch().read_bytes(),self.data)

    def test_wrong_range_or_size_never_publishes(self):
        self.seed(self.data[:4])
        response=Response(self.data[4:],status=206,start=3,total=len(self.data))
        with patch.object(cache,'open_https',return_value=response),self.assertRaisesRegex(ValueError,'unexpected response'):
            self.fetch()
        self.assertFalse((self.partial.parent/'owned.zip').exists())
        with patch.object(cache,'open_https',return_value=Response(self.data+b'excess')),self.assertRaisesRegex(ValueError,'size'):
            self.fetch()

    def test_bad_hash_is_not_cached_and_explicit_retry_can_succeed(self):
        with patch.object(cache,'open_https',return_value=Response(b'x'*len(self.data))),self.assertRaisesRegex(ValueError,'verification'):
            self.fetch()
        self.assertFalse(self.partial.exists())
        with patch.object(cache,'open_https',return_value=Response(self.data)):
            self.assertEqual(self.fetch().read_bytes(),self.data)

    def test_temporary_http_failures_retry_but_missing_file_does_not(self):
        unavailable=HTTPError('https://publisher.example/archive.zip',503,'Unavailable',{},None)
        with patch.object(cache,'open_https',side_effect=[unavailable,Response(self.data)]) as opened:
            self.fetch();self.assertEqual(opened.call_count,2)
        missing=HTTPError('https://publisher.example/archive.zip',404,'Missing',{},None)
        with patch.object(cache,'open_https',side_effect=missing) as opened,self.assertRaises(HTTPError):
            cache.fetch('missing.zip','https://publisher.example/missing.zip',1,'0'*64,Mock(),lambda:False,root=self.root)
        self.assertEqual(opened.call_count,1)

    def test_retries_are_bounded(self):
        with patch.object(cache,'open_https',side_effect=TimeoutError('offline')) as opened,self.assertRaises(TimeoutError):self.fetch()
        self.assertEqual(opened.call_count,3)

    def test_partial_from_another_file_is_rejected_by_final_hash(self):
        self.seed(b'xxxx')
        with patch.object(cache,'open_https',return_value=Response(self.data[4:],status=206,start=4,total=len(self.data))),self.assertRaisesRegex(ValueError,'verification'):
            self.fetch()
        self.assertFalse(self.partial.exists())

    def test_https_and_filename_trust_boundaries(self):
        with self.assertRaisesRegex(ValueError,'secure connection'):
            cache.open_https(Request('http://publisher.example/archive.zip'))
        with self.assertRaisesRegex(ValueError,'secure connection'):
            cache.SecureRedirect().redirect_request(Request('https://publisher.example/archive.zip'),None,302,'',{},'http://insecure.example/archive.zip')
        with self.assertRaises(ValueError):
            cache.fetch('../escape.zip','https://publisher.example/a',1,self.sha,Mock(),lambda:False,root=self.root)


class UpstreamCheckTests(unittest.TestCase):
    def test_available_file_must_have_exact_size_and_zip_prefix(self):
        pin=dict(url='https://publisher.example/a',size=100,sha256='0'*64)
        response=Response(b'PK\x03\x04'+b'a'*28,status=206,start=0,total=100)
        with patch.object(upstream_check,'open_https',return_value=response):
            self.assertEqual(upstream_check.probe('owned',pin)['bytes'],100)
        response=Response(b'<html>sign in</html>',status=200)
        with patch.object(upstream_check,'open_https',return_value=response),self.assertRaises(ValueError):upstream_check.probe('owned',pin)


if __name__=='__main__':unittest.main()
