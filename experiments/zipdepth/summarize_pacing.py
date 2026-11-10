"""Join bounded worker/broker/output timestamps from the owned-source probe."""
import argparse
import json
from pathlib import Path

import numpy as np


def summarize(path):
    report = json.loads(path.read_text(encoding='utf-8'))
    worker = json.loads(path.with_suffix('.worker.json').read_text(encoding='utf-8'))
    assert report['completed'] and not report['errors']
    work = {row[0]: row for row in worker['rows']}
    publication = dict(report['timing_trace']['publications'])
    begin, end = report['rows'][0]['begin_ns'], report['rows'][-1]['end_ns']
    rows = [row for row in report['timing_trace']['outputs'] if begin < row[0] <= end]
    assert all(seq in work and seq in publication for _, seq, _, _ in rows)

    def quantiles(values):
        return dict(zip(('min', 'p50', 'p95', 'p99', 'max'),
                        np.percentile(values, [0, 50, 95, 99, 100]).tolist()))

    result = dict(samples=len(rows), scope='Monotonic CPU timestamps; broker publish to Qt afterFrameEnd, not scanout.')
    result['work_interval_ms'] = quantiles(np.diff([row[2] for row in worker['rows']
                                                   if begin < row[2] <= end]) / 1e6)
    for name, values in (
        ('work_ms', [(work[s][3] - work[s][2]) / 1e6 for _, s, _, _ in rows]),
        ('ready_to_publish_ms', [(publication[s] - work[s][3]) / 1e6 for _, s, _, _ in rows]),
        ('publish_to_output_ms', [(t - publication[s]) / 1e6 for t, s, _, _ in rows]),
        ('callback_to_output_ms', [(t - cb) / 1e6 for t, _, _, cb in rows]),
    ):
        result[name] = quantiles(values)
    result['callback_age_over_25ms'] = sum(t - cb > 25e6 for t, _, _, cb in rows)
    result['broker_age_over_10ms'] = sum(t - publication[s] > 10e6 for t, s, _, _ in rows)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('paths', nargs='+', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    results = {path.stem: summarize(path) for path in args.paths}
    args.output.write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(json.dumps(results, indent=2))
