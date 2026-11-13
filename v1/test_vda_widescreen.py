"""Bounded 4K HEVC and original-profile tests through the public launcher."""
import argparse
import json
from pathlib import Path
import subprocess
import uuid

import cv2
import numpy as np
import torch

from screento3d_app import pipeline
from screento3d_app.resources import configure_media_tools
from screento3d_app.vda_backend import VdaEngine
from screento3d_app.vda_preprocess import preprocess
from vda_streaming_experiment import ROOT, VdaStreamingEngine


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--widescreen', type=Path, required=True)
    parser.add_argument('--original', type=Path, required=True)
    args = parser.parse_args()
    root = ROOT/'out/vda-widescreen'/uuid.uuid4().hex
    root.mkdir(parents=True)
    media = ROOT/'out/gpu-preview/ScreenTo3D-GPU-Preview/_internal/ffmpeg'
    configure_media_tools(media)
    report = dict(passed=False, jobs=[], scope='Short upscaled 4K compatibility fixture, not native 4K quality or performance')
    try:
        fixture = root/'input-4k-hevc.mp4'
        subprocess.run([str(media/'ffmpeg.exe'), '-v', 'error', '-i', str(args.widescreen),
            '-vf', 'scale=3840:2160,setsar=1', '-r', '24', '-frames:v', '12', '-t', '0.5',
            '-c:v', 'hevc_nvenc', '-cq', '18', '-tag:v', 'hvc1', '-c:a', 'aac', str(fixture)],
            check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        cap = cv2.VideoCapture(str(fixture))
        try:
            ok, bgr = cap.read()
            assert ok
            frame = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        finally:
            cap.release()
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        with VdaStreamingEngine() as oracle:
            # Direct pinned source API: the old diagnostic adapter caps inputs at 1920.
            expected = oracle.model.infer_video_depth_one(frame, input_size=518, device='cuda', fp32=True)
            np.testing.assert_array_equal(preprocess(frame, (518, 924)),
                oracle.model.transform({'image': frame.astype(np.float32)/255})['image'])
        with VdaEngine(ROOT/'out/vda-local/518x924-fp32', Path('C:/TensorRT/TensorRT-11.2.1.2/bin')) as engine:
            actual = engine.infer(frame)[0]
            np.testing.assert_allclose(actual, expected, atol=.001, rtol=.001)
            report['4k_depth_max_abs'] = float(np.abs(actual-expected).max())
        for label, source, codec, shape in (
            ('original', args.original, 'h264', [1, 1, 3, 518, 896]),
            ('4k', fixture, 'hevc', [1, 1, 3, 518, 924])):
            output = root/f'{label}-sbs.mp4'
            result = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                str(ROOT/'scripts/run-vda.ps1'), '-InputVideo', str(source), '-OutputVideo', str(output),
                '-OutputCodec', codec], text=True, encoding='utf-8', capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW)
            (root/f'{label}-stdout.jsonl').write_text(result.stdout, encoding='utf-8')
            (root/f'{label}-stderr.txt').write_text(result.stderr, encoding='utf-8')
            assert result.returncode == 0, result.stderr
            events = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
            complete = next(event for event in events if event['event'] == 'complete')
            selected = next(event for event in events if event['event'] == 'vda_profile')
            assert selected['input_shape'] == shape
            assert complete['telemetry']['resources']['input_shape'] == shape
            before = pipeline.probe_video(source, output_codec=codec)
            # Raw probe: an 8K-wide SBS is not a supported new 2D conversion input.
            raw = subprocess.check_output([str(media/'ffprobe.exe'), '-v', 'error', '-show_streams', '-of', 'json', str(output)], text=True)
            streams = json.loads(raw)['streams']
            video = next(stream for stream in streams if stream['codec_type'] == 'video')
            assert video['width'] == before['width']*2 and video['height'] == before['height']
            assert int(video['nb_frames']) == complete['frames'] == before['total_frames']
            assert video['codec_name'] == codec
            assert any(stream['codec_type'] == 'audio' for stream in streams) == before['has_audio']
            if label == '4k':
                assert video['codec_tag_string'] == 'hvc1' and complete['frames'] == 12
            cap = cv2.VideoCapture(str(output))
            try:
                decoded = 0
                while True:
                    ok, image = cap.read()
                    if not ok:
                        break
                    if decoded == 0:
                        cv2.imwrite(str(root/f'{label}-first-frame.jpg'), cv2.resize(image, (1536, 432)))
                    decoded += 1
                assert decoded == complete['frames']
            finally:
                cap.release()
            report['jobs'].append(dict(name=label, complete=complete, output_video=video))
            print('PASS: '+label+' through public launcher', flush=True)
        report['passed'] = True
    finally:
        (root/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(root/'report.json', flush=True)


if __name__ == '__main__':
    main()
