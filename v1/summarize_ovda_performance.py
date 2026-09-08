"""Summarize whole-job repetitions and explicitly device-wide observations."""
import json
from pathlib import Path
import statistics

ROOT=Path(__file__).resolve().parents[1]


def main():
    folders={'original':'8d70b8a3d87441de89285a239898b9a9','1080':'ad09b1729f93444492f67699e5ca1d55'}
    results={}
    for name,token in folders.items():
        root=ROOT/'out/ovda-expansion-evaluation'/token
        report=json.loads((root/'report.json').read_text())
        assert report['passed']
        groups={}
        for renderer,group in report['benchmark'].items():
            runs=group['runs'][1:];assert len(runs)==5
            assert all(r['telemetry']['diagnostic_hashes'] is None for r in runs)
            samples=[];errors=0
            for index in range(1,6):
                rows=json.loads((root/f'benchmark-{renderer}-{index}.gpu.json').read_text())
                for row in rows:
                    if row['returncode']!=0:errors+=1;continue
                    try:
                        fields=[x.strip() for x in row['value'].split(',')]
                        samples.append(dict(memory_mib=float(fields[1]),gpu_percent=float(fields[2]),
                            encoder_percent=float(fields[3]),decoder_percent=float(fields[4]),power_w=float(fields[5])))
                    except (ValueError,IndexError):errors+=1
            groups[renderer]=dict(median_fps=group['median_fps'],fps_range=[group['min_fps'],group['max_fps']],
                median_process_wall_seconds=statistics.median(r['process_wall_seconds'] for r in runs),
                median_stage_ms={stage:statistics.median(r['telemetry']['stages'][stage]['mean_ms'] for r in runs)
                    for stage in ('decode_read','depth_inference','temporal_stereo','encode_write','frame_total')},
                max_torch_allocated_bytes=max(r['torch_peak_allocated_bytes'] for r in runs),
                device_memory_mib_range=[min(s['memory_mib'] for s in samples),max(s['memory_mib'] for s in samples)] if samples else None,
                device_gpu_percent_range=[min(s['gpu_percent'] for s in samples),max(s['gpu_percent'] for s in samples)] if samples else None,
                observation_count=len(samples),observation_errors=errors)
        groups['cuda_speedup']=groups['cuda']['median_fps']/groups['cpu']['median_fps']
        groups['note']='One discarded warmup + five repetitions; short clips, no sustained claim. Torch peak excludes TRT/NVENC. nvidia-smi is sampled device-wide incl. resident desktop/Comfy workload, not model VRAM.'
        results[name]=groups
        (root/'performance-summary.json').write_text(json.dumps(groups,indent=2))
    print(json.dumps(results,indent=2))


if __name__=='__main__':main()
