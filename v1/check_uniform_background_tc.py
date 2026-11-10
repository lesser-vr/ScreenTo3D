"""Run the pinned local natural-video TC; failure/inconclusive never count as pass."""
import argparse
import json
from pathlib import Path
import sys
from uniform_background_tc import load_case,verify_asset,inspect_clip,assess_performance,ROOT


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--media-only',action='store_true')
    parser.add_argument('--model',choices=('ovda-small-c16','da2-base','da2-small','vda-small'),default='ovda-small-c16')
    parser.add_argument('--windows',type=int,choices=(2,3),default=3)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    result=dict(status='failed',model=args.model)
    try:
        case=load_case();path=verify_asset(case)
        result.update(case_id=case['id'],sha256=case['sha256'],media=inspect_clip(path,case))
        if args.media_only:result['status']='passed-media-only'
        else:
            sys.path.insert(0,str(ROOT/'experiments/ovda'))
            import analyze_uniform_background
            sys.argv=[sys.argv[0],'--output',str(args.output/'native'),'--media',str(path.parent),
                      '--clip','flower','--windows',str(args.windows),'--normal-policy','--model',args.model]
            analyze_uniform_background.main()
            report=json.loads((args.output/'native/report.json').read_text())
            if not report.get('completed') or report['media_hashes'].get('flower')!=case['sha256']:
                raise ValueError('Incomplete or different-source native measurement')
            result.update(assess_performance(report,case))
    except Exception as error:result['error']=str(error)
    finally:(args.output/'report.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result),flush=True)
    return 0 if result['status'] in ('passed','passed-media-only') else 1


if __name__=='__main__':raise SystemExit(main())
