"""Real FFmpeg publication/PTS/audio/child cleanup with an explicit synthetic depth backend."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import subprocess
from unittest.mock import patch

import numpy as np

from depthsbs_app import pipeline, resources
from depthsbs_app.depth_backend import BackendBinding, BackendSpec


def run_tool(command):
    return subprocess.run(command, capture_output=True, text=True, check=True, timeout=60,
                          creationflags=subprocess.CREATE_NO_WINDOW)


def probe(ffprobe, path):
    return json.loads(run_tool([str(ffprobe), '-v', 'error', '-count_frames',
                               '-show_streams', '-of', 'json', str(path)]).stdout)['streams']


def verify_media(ffmpeg, ffprobe, source, output, frames, codec):
    original, converted = probe(ffprobe, source), probe(ffprobe, output)
    left = next(row for row in original if row['codec_type'] == 'video')
    right = next(row for row in converted if row['codec_type'] == 'video')
    assert right['codec_name'] == codec
    assert (right['width'], right['height']) == (left['width'] * 2, left['height'])
    assert int(left['nb_read_frames']) == int(right['nb_read_frames']) == frames
    fps = Fraction(left['avg_frame_rate'])
    assert Fraction(right['avg_frame_rate']) == fps
    stamps = json.loads(run_tool([str(ffprobe), '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'frame=best_effort_timestamp_time', '-of', 'json', str(output)]).stdout)['frames']
    pts = [float(row['best_effort_timestamp_time']) for row in stamps]
    assert len(pts) == frames
    assert all(abs(t - index / float(fps)) < 0.0001 for index, t in enumerate(pts))
    a, b = ([row for row in streams if row['codec_type'] == 'audio'] for streams in (original, converted))
    assert len(a) == len(b)
    for x, y in zip(a, b):
        assert abs(float(x['duration']) - float(y['duration'])) <= 1 / float(fps)
    run_tool([str(ffmpeg), '-v', 'error', '-xerror', '-i', str(output), '-f', 'null', '-'])
    return dict(frames=frames, fps=str(fps), geometry=[right['width'], right['height']],
                audio_streams=len(b), full_decode=True, pts_checked=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--media-tools', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--encoder', choices=['cpu', 'nvenc'], default='cpu')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    resources.configure_media_tools(args.media_tools)
    ffmpeg, ffprobe = (args.media_tools / (name + '.exe') for name in ('ffmpeg', 'ffprobe'))
    report = dict(status='failed', encoder=args.encoder, cases=[],
                  scope='Real media and owned child processes; synthetic depth, no depth-quality claim')
    try:
        for codec, rate, frames, audio in [('h264', '24', 24, True), ('hevc', '30000/1001', 30, False)]:
            source = args.output / f'source-{codec}.mp4'
            command = [str(ffmpeg), '-v', 'error', '-nostdin', '-f', 'lavfi', '-i',
                       f'testsrc2=size=128x128:rate={rate}']
            if audio:
                command += ['-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000']
            command += ['-t', str(frames / float(Fraction(rate))), '-c:v', 'libx264', '-preset', 'ultrafast',
                        '-pix_fmt', 'yuv420p']
            if audio:
                command += ['-c:a', 'aac', '-shortest']
            command += [str(source)]
            run_tool(command)
            source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            for scenario in ('success', 'cancel', 'encoder_failure'):
                destination = args.output / f'{codec}-{scenario}.mp4'
                destination.write_bytes(b'previous output')
                stale = destination.with_suffix('.mp4.partial.mp4')
                stale.write_bytes(b'unowned stale artifact')
                cancel = args.output / 'cancel.token'
                children, events = [], []

                class Engine:
                    def __enter__(self): return self
                    def __exit__(self, *ignored): return False
                    def infer(self, value):
                        if scenario == 'cancel': cancel.touch()
                        return np.zeros((1, 128, 128), np.float32)
                    def telemetry(self): return {'synthetic_depth': True}

                backend = BackendBinding(BackendSpec('synthetic-test', 'test-only'),
                                         lambda progress: Engine(), lambda frame: frame)
                actual_popen = subprocess.Popen

                def spawn(command, **kwargs):
                    command = list(command)
                    if 'pipe:0' in command:
                        if args.encoder == 'cpu':
                            command[command.index('-c:v') + 1] = 'libx264' if codec == 'h264' else 'libx265'
                            command[command.index('-preset') + 1] = 'ultrafast'
                            for key in ('-tune', '-rc', '-cq'):
                                index = command.index(key)
                                del command[index:index + 2]
                            command[-1:-1] = ['-crf', '18']
                        if scenario == 'encoder_failure':
                            command[command.index('-c:v') + 1] = 'depthsbs_intentionally_invalid_encoder'
                    process = actual_popen(command, **kwargs)
                    children.append(process)
                    return process

                try:
                    with patch.object(pipeline.subprocess, 'Popen', side_effect=spawn):
                        result = pipeline.convert_video(source, destination, 'balanced', events.append, cancel,
                                                        output_codec=codec, depth_backend=backend)
                    assert scenario == 'success', 'Expected failure was not raised'
                    assert events[-1]['event'] == 'complete' and result['frames'] == frames
                    details = verify_media(ffmpeg, ffprobe, source, destination, frames, codec)
                except (InterruptedError, RuntimeError, OSError) as error:
                    if scenario == 'success': raise
                    if scenario == 'cancel':
                        assert isinstance(error, InterruptedError)
                        assert any(event['event'] == 'cancelled' for event in events)
                    else:
                        assert any(child.poll() not in (None, 0) for child in children)
                    assert destination.read_bytes() == b'previous output'
                    assert not any(event['event'] == 'complete' for event in events)
                    details = dict(previous_output_preserved=True)
                assert all(child.poll() is not None for child in children)
                assert not cancel.exists()
                assert not list(args.output.glob(f'.{destination.name}.*.mp4'))
                assert stale.read_bytes() == b'unowned stale artifact'
                assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
                report['cases'].append(dict(codec=codec, scenario=scenario, passed=True, **details))
        report['status'] = 'passed'
    finally:
        (args.output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
