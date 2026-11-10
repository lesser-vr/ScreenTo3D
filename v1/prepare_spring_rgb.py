"""Add only held-out right-camera RGB/disparity for the existing Spring subset."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import json
from pathlib import Path,PurePosixPath
from prepare_spring_subset import ROOT,archive_index,extract_member


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=ROOT/'out/spring-source')
    args=p.parse_args()
    source=json.loads((args.root/'manifest.json').read_text())
    if not source['completed']:raise ValueError('Prepare original Spring subset first')
    metadata=json.loads((args.root/'dataset.json').read_text(encoding='utf-8-sig'))
    records={f['dataFile']['filename']:{k:f['dataFile'][k] for k in ('filename','id','filesize','md5')}
             for f in metadata['data']['latestVersion']['files']}
    selected=[]
    for name in ('train_frame_right.zip','train_disp1_right.zip'):
        for member in archive_index(records[name],args.root):
            path=PurePosixPath(member['name']);frame=int(path.stem.rsplit('_',1)[-1])
            if path.parts[2] in source['plan']['sequences'] and 49<=frame<=80:selected.append((records[name],member))
    if len(selected)!=256 or sum(m['size'] for _,m in selected)>2*1024**3:raise ValueError('Unexpected right-camera subset')
    plan=dict(sequences=source['plan']['sequences'],frames=[49,80],members=len(selected),
        compressed_bytes=sum(m['compressed'] for _,m in selected),bytes=sum(m['size'] for _,m in selected))
    print(json.dumps(plan),flush=True)
    entries=[]
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            jobs=[pool.submit(extract_member,r,m,args.root) for r,m in selected]
            for job in as_completed(jobs):
                entries.append(job.result())
                if len(entries)%32==0:print('Right-camera verified',len(entries),'/',len(jobs),flush=True)
    finally:
        (args.root/'right-manifest.json').write_text(json.dumps(dict(completed=len(entries)==len(selected),plan=plan,
            attribution=source['attribution'],entries=entries),indent=2))


if __name__=='__main__':main()
