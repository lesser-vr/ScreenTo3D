"""Summarize the paired public 4K120 runs, retaining the measurement scopes."""
import argparse,json
from pathlib import Path
from statistics import median
ROOT=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser()
parser.add_argument('--prefix',choices=['opt','guide'],default='opt')
parser.add_argument('--caps',type=int,nargs='+',choices=[0,30,60],default=[0,60,30])
parser.add_argument('--output',type=Path,default=ROOT/'out/gpu-load-opt/summary.json')
args=parser.parse_args()
rows=[]
for cap in args.caps:
    for revision in ('before','after'):
        tag=f'{args.prefix}-{revision}-{cap}'
        telemetry=json.loads((ROOT/f'out/public-hfr/{tag}.json').read_text())
        run=json.loads((ROOT/f'out/public-hfr/Jockey-zipdepth-{tag}.json').read_text())
        assert telemetry['completed'] and run['completed'] and not run['errors']
        assert len(run['rows'])==5 and run['cleanup']['live_pools']==run['cleanup']['live_nodes']==0
        assert all(r['sample_coverage']==1 for r in run['rows'])
        samples=run['rows'];gpu=telemetry['cases'][0]['telemetry']
        row=dict(cap=cap,revision=revision,output_fps=median(r['output_fps'] for r in samples),
            output_fps_range=[min(r['output_fps'] for r in samples),max(r['output_fps'] for r in samples)],
            received_fps=median(r['received_fps'] for r in samples),
            callback_age_p50_ms=median(r['callback_age_p50_ms'] for r in samples),
            callback_age_p95_ms=median(r['callback_age_p95_ms'] for r in samples),
            gpu_mean_pct=gpu['utilization.gpu']['mean'],power_mean_w=gpu['power.draw']['mean'],
            vram_mib=gpu['memory.used']['mean'])
        rows.append(row)
        print(f"| {revision} | {cap or 'unlimited'} | {row['output_fps']:.2f} | {row['gpu_mean_pct']:.2f}% | {row['power_mean_w']:.2f} | {row['callback_age_p50_ms']:.2f} |")
args.output.write_text(json.dumps(dict(rows=rows,
    scope='RTX 5090, UVG Jockey 4K120, 7680x2160 native window, five 10s windows per session; whole GPU, callback to distinct Qt afterFrameEnd, not physical latency'),indent=2))
