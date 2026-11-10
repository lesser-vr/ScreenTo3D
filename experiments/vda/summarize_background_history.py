"""Summarize bounded numeric reset traces; no pixels or GPU runtime required."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
import statistics


def distribution(values):
    values=sorted(value/1e6 for value in values if value is not None)
    if not values:return None
    p=.95*(len(values)-1);lo=int(p);hi=min(lo+1,len(values)-1)
    return dict(min_ms=values[0],median_ms=statistics.median(values),p95_ms=values[lo]+(values[hi]-values[lo])*(p-lo),max_ms=values[-1])


def summarize(root):
    groups=defaultdict(list);sessions=[]
    for path in sorted((root/'history').glob('*.json')):
        data=json.loads(path.read_text())
        sessions.append(dict(file=path.name,seen=data['seen'],retained=data['retained']))
        key='on' if data['background'] is not False else 'off'
        groups[key].extend(row for row in data['samples'] if row['processed']>=80)
    result=dict(warmup_exclusion='processed index <80',sessions=sessions,groups={})
    for name,rows in groups.items():
        gaps=[row for row in rows if row['reason']=='gap']
        result['groups'][name]=dict(samples=len(rows),reason_counts=dict(Counter(row['reason'] or 'retain' for row in rows)),
            gap_sequence_steps=dict(Counter(row['sequence_step'] for row in gaps)),
            gap_cut_true=sum(row['cut'] for row in gaps),
            gap_single_skip_would_retain=sum(row['single_skip_reason'] is None for row in gaps),
            gap_source_delta=distribution(row['source_step_ns'] for row in gaps),
            all_sequence_steps=dict(Counter(row['sequence_step'] for row in rows)),
            stage_intervals={kind:{key:distribution(row[key] for row in selected) for key in
                ('source_step_ns','decision_interval_ns','capture_ns','previous_total_ns',
                 'previous_depth_ns','previous_stereo_ns','previous_background_ns')} for kind,selected in (('all',rows),('gaps',gaps))})
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path)
    args=parser.parse_args();result=summarize(args.root)
    (args.root/'history-summary.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result),flush=True)


if __name__=='__main__':main()
