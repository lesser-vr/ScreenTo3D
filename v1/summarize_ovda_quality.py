"""Join verified matching-frame evidence; do not interpret MAE as visual truth."""
import csv
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    current=ROOT/'out/ovda-expansion-evaluation/d6595c357e654ebfb6fba313845cbf9e'
    avatar=json.loads((current/'report.json').read_text())
    prior=json.loads((ROOT/'out/ovda-trt-integration/7b440058ea7d40bf97893b8c9a8d5043/report.json').read_text())
    c8=json.loads((ROOT/'out/ovda-c8-quality/c66cf4b505fe4d5b820858964b3a5a3e/report.json').read_text())
    assert avatar['passed'] and prior['passed'] and c8['passed']
    rows=[]
    baselines={}
    for model,result in avatar['quality'].items():
        rows.append(dict(clip='avatar',model=model,**result['temporal']['summary']))
    baselines['avatar']=(avatar['quality']['ovda']['input_sha256'],avatar['quality']['ovda'],avatar['quality']['ovda']['temporal']['summary'])
    for clip in prior['clips']:
        for model,summary in clip['reference_temporal'].items():rows.append(dict(clip=clip['name'],model=model,**summary))
        rows.append(dict(clip=clip['name'],model='ovda',**clip['temporal']['summary']))
        baselines[clip['name']]=(clip['input_sha256'],clip['result'],clip['temporal']['summary'])
    comparisons=[]
    for clip in c8['clips']:
        digest,result,summary=baselines[clip['name']]
        assert clip['input_sha256']==digest
        assert result['frames']==clip['result']['frames']
        assert result['telemetry']['diagnostic_hashes']['decoded_rgb']==clip['result']['telemetry']['diagnostic_hashes']['decoded_rgb']
        rows.append(dict(clip=clip['name'],model='ovda-c8',**clip['temporal']['summary']))
        comparisons.append(dict(clip=clip['name'],ratios={key:clip['temporal']['summary'][key]/summary[key]
            for key in ('aligned_mae','edge_aligned_mae')}))
    columns=('clip','model','aligned_mae','edge_aligned_mae','unaligned_mae','valid_fraction','edge_valid_fraction')
    with (current/'quality-summary.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=columns,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
    report=dict(passed=True,rows=rows,c8_vs_c16=comparisons,
        decision='Keep DA2 Small mode defaults; explicit oVDA stays c16 FP32. c8 has mixed/worse temporal-edge results; FP16 numerical gate failed.',
        note='Seven matched clips, source-flow normalized raw-depth proxies. No ground-truth depth, blinded VR review or total-quality ranking.')
    (current/'quality-summary.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(comparisons,indent=2))


if __name__=='__main__':main()
