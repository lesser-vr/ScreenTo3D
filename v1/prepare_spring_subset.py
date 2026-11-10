"""Bounded, resumable HTTP-range extraction from the official Spring V2 archives."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib
import io
import json
from pathlib import Path,PurePosixPath
import struct
import time
import urllib.request
import zipfile
import zlib

ROOT=Path(__file__).resolve().parents[1]
BASE='https://darus.uni-stuttgart.de/api/access/datafile/'
METADATA='https://darus.uni-stuttgart.de/api/datasets/:persistentId/?persistentId=doi:10.18419/darus-3376'
ARCHIVES=('train_frame_left.zip','train_disp1_left.zip','train_flow_FW_left.zip','train_disp2_FW_left.zip')


def get_range(url,start,length,total):
    if length<=0:return b''
    if length>128*1024**2 or start<0 or start+length>total:raise ValueError('Unbounded archive range')
    request=urllib.request.Request(url,headers={'Range':f'bytes={start}-{start+length-1}','Accept-Encoding':'identity'})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request,timeout=40) as response:
                expected=f'bytes {start}-{start+length-1}/{total}'
                if response.status!=206 or response.headers.get('Content-Range')!=expected:
                    raise ValueError('Server did not honor exact bounded range')
                data=response.read(length+1)
                if len(data)!=length:raise ValueError('Short archive range')
                return data
        except (OSError,TimeoutError):
            if attempt==3:raise
            time.sleep(attempt+1)


class RemoteArchive(io.RawIOBase):
    def __init__(self,url,size):self.url,self.size,self.position=url,size,0
    def seekable(self):return True
    def tell(self):return self.position
    def seek(self,offset,whence=0):
        position=offset+(self.position if whence==1 else self.size if whence==2 else 0)
        if position<0 or position>self.size:raise ValueError('Archive seek outside bounds')
        self.position=position;return position
    def read(self,n=-1):
        n=self.size-self.position if n<0 else min(n,self.size-self.position)
        data=get_range(self.url,self.position,n,self.size);self.position+=len(data);return data


def archive_index(record,cache):
    path=cache/(record['filename']+'.index.json')
    if path.exists():
        saved=json.loads(path.read_text())
        if saved['archive']==record:return saved['members']
    with zipfile.ZipFile(RemoteArchive(BASE+str(record['id']),record['filesize'])) as archive:
        members=[dict(name=x.filename,offset=x.header_offset,size=x.file_size,compressed=x.compress_size,
                      method=x.compress_type,crc=x.CRC,flags=x.flag_bits) for x in archive.infolist() if not x.is_dir()]
    path.write_text(json.dumps(dict(archive=record,members=members),indent=2))
    return members


def extract_member(record,member,destination):
    name=PurePosixPath(member['name'])
    if name.is_absolute() or '..' in name.parts or name.parts[:2]!=('spring','train') or any(c in member['name'] for c in ('\\',':')):
        raise ValueError('Unsafe Spring member path')
    if member['size']>100*1024**2 or member['flags']&1 or member['method'] not in (0,8):
        raise ValueError('Unsupported Spring member')
    path=destination.joinpath(*name.parts)
    if not path.resolve().is_relative_to(destination.resolve()):raise ValueError('Spring member escaped destination')
    data=path.read_bytes() if path.exists() else None
    if data is None or len(data)!=member['size'] or zlib.crc32(data)!=member['crc']:
        # Local filename/extra headers fit in the uint16 lengths from the ZIP header.
        url=BASE+str(record['id']);offset=member['offset'];size=record['filesize']
        header=get_range(url,offset,30,size)
        fields=struct.unpack('<4s5H3I2H',header)
        if fields[0]!=b'PK\x03\x04':raise ValueError('Invalid local ZIP header')
        fn,extra=fields[-2:]
        body=get_range(url,offset+30,fn+extra+member['compressed'],size)
        if body[:fn].decode('utf-8' if fields[2]&2048 else 'cp437')!=member['name']:
            raise ValueError('ZIP member identity mismatch')
        compressed=body[fn+extra:]
        if member['method']==0:data=compressed
        else:
            decoder=zlib.decompressobj(-15)
            data=decoder.decompress(compressed,member['size']+1)
            if not decoder.eof or decoder.unconsumed_tail:raise ValueError('Unbounded compressed member')
        if len(data)!=member['size'] or zlib.crc32(data)!=member['crc']:raise ValueError('ZIP CRC mismatch')
        path.parent.mkdir(parents=True,exist_ok=True)
        temporary=path.with_suffix(path.suffix+'.partial');temporary.write_bytes(data);temporary.replace(path)
    return dict(path=member['name'],sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),archive=record['filename'],crc32=member['crc'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT/'out/spring-source')
    parser.add_argument('--download',action='store_true')
    args=parser.parse_args();args.root.mkdir(parents=True,exist_ok=True)
    metadata_path=args.root/'dataset.json'
    if not metadata_path.exists():
        with urllib.request.urlopen(METADATA,timeout=30) as response:
            data=response.read(2*1024**2+1)
        if len(data)>2*1024**2:raise ValueError('Oversized dataset metadata')
        metadata_path.write_bytes(data)
    metadata=json.loads(metadata_path.read_text(encoding='utf-8-sig'))
    version=metadata['data']['latestVersion']
    if (version['versionNumber'],version['versionMinorNumber'])!=(2,0) or version['license']['name']!='CC BY 4.0':
        raise ValueError('Spring version/license differs from reviewed V2')
    records={f['dataFile']['filename']:{k:f['dataFile'][k] for k in ('filename','id','filesize','md5')}
             for f in metadata['data']['latestVersion']['files']}
    indexes={name:archive_index(records[name],args.root) for name in ARCHIVES}
    images=indexes[ARCHIVES[0]]
    sequences=sorted({PurePosixPath(x['name']).parts[2] for x in images})
    eligible=[s for s in sequences if sum(PurePosixPath(x['name']).parts[2]==s for x in images)>=80]
    chosen=[eligible[round(i*(len(eligible)-1)/3)] for i in range(4)]
    selected=[]
    for archive,members in indexes.items():
        for member in members:
            path=PurePosixPath(member['name'])
            frame=int(path.stem.rsplit('_',1)[-1])
            if path.parts[2] not in chosen:continue
            # 1-32 warmup, 33-48 calibration, 49-80 evaluation.
            # Forward temporal truth is required only for evaluated pairs 49->50 ... 79->80.
            use=1<=frame<=80 if archive in ARCHIVES[:2] else 49<=frame<=79
            if use:selected.append((records[archive],member))
    plan=dict(dataset='doi:10.18419/DARUS-3376',version='2.0',license='CC BY 4.0',
              selection='four evenly spaced sorted eligible training IDs; first 80 frames, chosen before model evaluation',
              sequences=chosen,warmup=[1,32],calibration=[33,48],evaluation=[49,80],
              archives=records,members=[dict(archive=r['filename'],**m) for r,m in selected],
              compressed_bytes=sum(m['compressed'] for _,m in selected),bytes=sum(m['size'] for _,m in selected))
    (args.root/'plan.json').write_text(json.dumps(plan,indent=2))
    if len(set(chosen))!=4 or len(selected)!=4*(80*2+31*2) or plan['bytes']>6*1024**3:
        raise ValueError('Unexpected or oversized Spring subset')
    print(json.dumps({k:v for k,v in plan.items() if k not in ('members','archives')}),flush=True)
    if not args.download:return
    entries=[];started=time.monotonic()
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            jobs=[pool.submit(extract_member,r,m,args.root) for r,m in selected]
            for job in as_completed(jobs):
                entries.append(job.result())
                if len(entries)%20==0:print(f'Downloaded/verified {len(entries)}/{len(jobs)} members in {time.monotonic()-started:.1f}s',flush=True)
    finally:
        (args.root/'manifest.json').write_text(json.dumps(dict(completed=len(entries)==len(selected),plan=plan,
            attribution='Mehl et al. 2023, Spring, DaRUS V2, doi:10.18419/DARUS-3376; CC BY 4.0. Subset extraction only; no endorsement.',
            entries=sorted(entries,key=lambda x:x['path'])),indent=2))
    print('Spring subset complete',flush=True)


if __name__=='__main__':main()
