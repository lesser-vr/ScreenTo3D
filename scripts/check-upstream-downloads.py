"""Check pinned upstream downloads before release; --full verifies whole archives."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'v1'))
from depthsbs_app.official_sources import ARTIFACTS,fetch_artifact
from depthsbs_app.upstream_check import check
from depthsbs_app.optional_models import model_downloads,PACKS
from depthsbs_app.download_cache import fetch


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full',action='store_true')
    parser.add_argument('--cache',type=Path)
    parser.add_argument('--models',action='store_true',help='Also check the fixed public Base/VDA model release')
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    report=dict(passed=False,mode='full hash' if args.full else 'anonymous availability')
    try:
        report['sources']=check(ARTIFACTS,list(ARTIFACTS))
        if args.models:report['models']=check(model_downloads(),model_downloads())
        if args.full:
            for key in ARTIFACTS:fetch_artifact(key,lambda *_:None,lambda:False,root=args.cache)
            if args.models:
                for key,pin in model_downloads().items():
                    fetch(PACKS[key].filename,pin['url'],pin['size'],pin['sha256'],lambda *_:None,lambda:False,root=args.cache)
        report['passed']=True
    except Exception as error:report['error']=str(error)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
