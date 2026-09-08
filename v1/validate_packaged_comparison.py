"""Validate recorded media and parity independently of timing collection."""
import argparse
from fractions import Fraction
import json
from pathlib import Path
import subprocess


def validate(source, report_path):
    repo = Path(__file__).resolve().parents[1]
    ffprobe = repo / 'out/gpu-preview/DepthSBS-GPU-Preview/_internal/ffmpeg/ffprobe.exe'
    def probe(path):
        return json.loads(subprocess.check_output([str(ffprobe), '-v', 'error', '-count_frames',
            '-show_streams', '-of', 'json', str(path)]))['streams']
    original = probe(source)
    video = next(s for s in original if s['codec_type'] == 'video')
    report = json.loads(report_path.read_text(encoding='utf-8'))
    assert report['passed']
    hashes = []
    for run in report['runs']:
        completion = run['completion']
        streams = probe(completion['output'])
        converted = next(s for s in streams if s['codec_type'] == 'video')
        assert converted['codec_name'] == report.get('output_codec', 'h264')
        assert converted['codec_tag_string'] == ('hvc1' if report.get('output_codec') == 'hevc' else 'avc1')
        assert converted['width'] == video['width'] * 2 and converted['height'] == video['height']
        assert int(converted['nb_read_frames']) == int(video['nb_read_frames']) == completion['frames']
        assert Fraction(converted['avg_frame_rate']) == Fraction(video['avg_frame_rate'])
        assert abs(float(converted['duration']) - float(video['duration'])) <= 1 / float(Fraction(video['avg_frame_rate']))
        source_audio = [s for s in original if s['codec_type'] == 'audio']
        output_audio = [s for s in streams if s['codec_type'] == 'audio']
        assert len(source_audio) == len(output_audio)
        for left, right in zip(source_audio, output_audio):
            assert abs(float(left['duration']) - float(right['duration'])) <= 1 / float(Fraction(video['avg_frame_rate']))
        if run['kind'] == 'diagnostic':
            hashes.append(completion['telemetry']['diagnostic_hashes'])
    assert hashes and all(h == hashes[0] for h in hashes)
    assert len({r['decoded_hash'] for r in report['runs']}) == 1
    result = dict(passed=True, checked_runs=len(report['runs']), source_probe=original,
                  matched_diagnostic_hashes=hashes[0], decoded_hash=report['runs'][0]['decoded_hash'])
    output = report_path.with_name('media-validation.json')
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    validate(args.input, args.report)
