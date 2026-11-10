"""Prepare and verify official LPIPS metric weights inside this workspace."""
import hashlib
import importlib.util
import json
from pathlib import Path
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
URL='https://download.pytorch.org/models/alexnet-owt-7be5be79.pth'
PIN='7be5be791159472b1fbf3c69796f7cb30dca7ad8466c2df70058c37116cdee02'
LINEAR_PIN='df73285e35b22355a2df87cdb6b70b343713b667eddbda73e1977e0c860835c0'
SIZE=244408911


def main():
    folder=ROOT/'out/sbs-metric-weights';target=folder/'hub/checkpoints/alexnet-owt-7be5be79.pth'
    target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists():
        temporary=target.with_suffix('.partial');digest=hashlib.sha256();size=0
        with urllib.request.urlopen(URL,timeout=30) as source,temporary.open('xb') as output:
            while chunk:=source.read(1024**2):
                size+=len(chunk)
                if size>SIZE:raise ValueError('Metric checkpoint exceeds pinned size')
                digest.update(chunk);output.write(chunk)
        if size!=SIZE or digest.hexdigest()!=PIN:raise ValueError('Official metric checkpoint identity mismatch')
        temporary.replace(target)
    if target.stat().st_size!=SIZE or hashlib.sha256(target.read_bytes()).hexdigest()!=PIN:
        raise ValueError('Existing LPIPS backbone differs from trusted bytes')
    spec=importlib.util.find_spec('lpips')
    if spec is None:raise RuntimeError('Install lpips==0.1.4 in the local metric dependency directory')
    linear=Path(spec.origin).parent/'weights/v0.1/alex.pth'
    if hashlib.sha256(linear.read_bytes()).hexdigest()!=LINEAR_PIN:raise ValueError('LPIPS linear weights differ from trusted bytes')
    receipt=dict(backbone_url=URL,backbone_sha256=PIN,backbone_bytes=SIZE,linear_sha256=LINEAR_PIN,
        linear_source='lpips==0.1.4 wheel; richzhang/PerceptualSimilarity v0.1/alex.pth',
        scope='evaluation metric weights only; not product depth model replacement')
    (folder/'provenance.json').write_text(json.dumps(receipt,indent=2))
    print('Official LPIPS weights verified')


if __name__=='__main__':main()
