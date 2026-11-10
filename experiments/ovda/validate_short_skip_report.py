"""Validate the declared sampled-timeline comparison contract without rerunning CUDA."""
import argparse
import json
from pathlib import Path


def validate(report):
    assert report['passed'] and len(report['phases'])==4
    natural=0;consecutive=0
    for phase in report['phases']:
        for values in phase['clips'].values():
            strict,retain,dense=(values[name] for name in ('strict','retain','dense'))
            assert strict['frames']==retain['frames']
            if phase['dropped']:
                natural+=1
                assert retain['resets']==dense['resets']<strict['resets']
                assert retain['full_context_fraction']>0 and retain['retained']>0
                for metric in ('raw_error','temporal_error','edge_error','sbs_mae'):
                    assert retain[metric]['mean']<=strict[metric]['mean'],(phase['size'],metric)
            else:
                consecutive+=retain['frames']
                for variant in (strict,retain):
                    assert all(variant[m]['max']==0 for m in ('raw_error','temporal_error','edge_error','sbs_mae'))
    assert natural==9 and consecutive==72
    return dict(passed=True,natural_cases=natural,consecutive_frames=consecutive,
                contract='No worse mean raw/temporal/edge/native-SBS difference to dense reference in each sampled case; no-drop exact parity')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report',type=Path)
    args=parser.parse_args()
    result=validate(json.loads(args.report.read_text()))
    args.report.with_name('comparison-contract.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))
