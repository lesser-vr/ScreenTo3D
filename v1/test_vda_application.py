"""GPU integration gate for the opt-in application VDA backend (not a soak)."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import threading
import uuid
from unittest.mock import patch

import cv2
import numpy as np
import torch

from screento3d_app import pipeline
from screento3d_app.depth_backend import vda_binding
from screento3d_app.resources import configure_media_tools
from screento3d_app.vda_backend import VdaEngine
from screento3d_app.vda_preprocess import preprocess
from screento3d_app.vda_artifacts import artifact_profiles, select_artifact, profile_shape
from vda_streaming_experiment import ROOT, VdaStreamingEngine


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--letterbox-refinement', action='store_true')
    parser.add_argument('--engine-dir', type=Path, default=ROOT/'out/vda-local/518x896-fp32')
    parser.add_argument('--runtime-dir', type=Path, default=Path('C:/TensorRT/TensorRT-11.2.1.2/bin'))
    args = parser.parse_args()
    root = ROOT/'out/vda-application'/uuid.uuid4().hex
    root.mkdir(parents=True)
    report = dict(passed=False, jobs=[], letterbox_refinement=args.letterbox_refinement)
    media = ROOT/'out/gpu-preview/ScreenTo3D-GPU-Preview/_internal/ffmpeg'
    configure_media_tools(media)
    binding = vda_binding(args.engine_dir, args.runtime_dir)
    try:
        cap = cv2.VideoCapture(str(args.input))
        try:
            ok, bgr = cap.read()
            if not ok:
                raise RuntimeError('Unreadable source')
            frame = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        finally:
            cap.release()
        selected = select_artifact(artifact_profiles(args.engine_dir), dict(width=frame.shape[1], height=frame.shape[0]))
        shape = profile_shape(frame.shape[1], frame.shape[0])
        report['profile'] = list(shape)
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        with VdaStreamingEngine() as oracle:
            reference = oracle.model.infer_video_depth_one(frame, input_size=518, device='cuda', fp32=True)
            expected = oracle.model.transform({'image': frame.astype(np.float32)/255.0})['image']
            np.testing.assert_array_equal(preprocess(frame, shape), expected)
        report['preprocess_exact'] = True
        with VdaEngine(selected, args.runtime_dir) as engine:
            first = engine.infer(frame)
            np.testing.assert_allclose(first[0], reference, atol=.001, rtol=.001)
            engine.infer(frame)
            engine.reset('scene_cut')
            np.testing.assert_array_equal(engine.infer(frame), first)
            errors = []
            def wrong_owner():
                try:
                    engine.close()
                except RuntimeError as error:
                    errors.append(str(error))
            thread = threading.Thread(target=wrong_owner)
            thread.start(); thread.join()
            assert errors and not engine.closed
        engine.close()
        assert engine.closed and not engine.history and not engine.engines
        report['reset_exact_and_owner_cleanup'] = True
        metadata = pipeline.probe_video(args.input)
        for kind in ('cancel', 'failure', 'success'):
            job = root/kind
            job.mkdir()
            output = job/'output.mp4'
            output.write_bytes(b'prior-output')
            cancel = job/'cancel.flag'
            engines, processes = [], []
            def factory(progress):
                current = VdaEngine(selected, args.runtime_dir, progress)
                engines.append(current)
                if kind == 'failure':
                    execute = current._execute
                    def fail(image):
                        if current.calls == (4 if args.letterbox_refinement else 1):
                            raise RuntimeError('injected inference failure')
                        return execute(image)
                    current._execute = fail
                return current
            def progress(event):
                if kind == 'cancel' and event['event'] == 'progress' and event['frame'] >= (4 if args.letterbox_refinement else 1):
                    cancel.touch()
            original = subprocess.Popen
            def track(*a, **kw):
                process = original(*a, **kw)
                processes.append(process)
                return process
            result = None
            try:
                with patch('subprocess.Popen', side_effect=track):
                    result = pipeline.convert_video(args.input, output, 'video-quality', progress, cancel,
                        depth_backend=replace(binding, engine_factory=factory), diagnostic_hashes=True,
                        letterbox_refinement=args.letterbox_refinement)
            except InterruptedError:
                assert kind == 'cancel'
            except RuntimeError as error:
                assert kind == 'failure' and str(error) == 'injected inference failure'
            else:
                assert kind == 'success'
            assert len(engines) == 1 and engines[0].closed and not engines[0].history and not engines[0].engines
            assert all(process.poll() is not None for process in processes)
            assert [p.name for p in job.iterdir()] == ['output.mp4']
            if kind != 'success':
                assert output.read_bytes() == b'prior-output'
            else:
                outmeta = pipeline.probe_video(output, output_codec='hevc')
                assert result['frames'] == outmeta['total_frames'] == metadata['total_frames']
                assert outmeta['width'] == metadata['width']*2 and outmeta['height'] == metadata['height']
                assert outmeta['has_audio'] == metadata['has_audio']
                report['output_metadata'] = outmeta
                if args.letterbox_refinement:
                    padding = result['telemetry']['stereo']['letterbox']
                    assert padding['enabled'] and padding['applied_frames'] > 0
                    assert padding['restored_frames'] == padding['applied_frames']
            report['jobs'].append(dict(kind=kind, passed=True, result=result))
            print('PASS: '+kind, flush=True)
        # Real HEVC input and public CLI worker, including a deterministic cut.
        fixture = root/'cut-input.mp4'
        writer = cv2.VideoWriter(str(fixture), cv2.VideoWriter_fourcc(*'mp4v'), 24, (frame.shape[1], frame.shape[0]))
        if not writer.isOpened():
            raise RuntimeError('Fixture encoder unavailable')
        try:
            for index in range(48):
                writer.write(cv2.cvtColor(frame if index < 24 else 255-frame, cv2.COLOR_RGB2BGR))
        finally:
            writer.release()
        hevc_input = root/'cut-hevc.mp4'
        subprocess.run([str(media/'ffmpeg.exe'), '-v', 'error', '-i', str(fixture), '-c:v', 'hevc_nvenc',
                        '-y', str(hevc_input)], check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        status = root/'worker.jsonl'
        process = subprocess.run([sys.executable, '-m', 'screento3d_app.main', '--worker', '--input', str(hevc_input),
            '--output', str(root/'cut-output-hevc.mp4'), '--mode', 'video-quality', '--output-codec', 'hevc',
            '--depth-backend', 'vda-small', '--vda-engine-dir', str(args.engine_dir),
            '--runtime-dir', str(args.runtime_dir), '--media-tools', str(media), '--status-file', str(status),
            *(['--letterbox-refinement'] if args.letterbox_refinement else [])],
            text=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        (root/'worker-stderr.txt').write_text(process.stderr, encoding='utf-8')
        assert process.returncode == 0, process.stderr
        events = [json.loads(line) for line in status.read_text(encoding='utf-8').splitlines()]
        complete = next(event for event in events if event['event'] == 'complete')
        assert complete['frames'] == 48
        assert complete['telemetry']['scene_cut_resets'] == 1
        assert complete['telemetry']['resources']['resets'] == 2
        if args.letterbox_refinement:
            assert complete['telemetry']['stereo']['letterbox']['scene_cut_resets'] == 1
        outmeta = pipeline.probe_video(root/'cut-output-hevc.mp4', output_codec='hevc')
        assert outmeta['codec'] == 'hevc' and outmeta['total_frames'] == 48
        report['public_worker_hevc_cut'] = complete
        report['passed'] = True
        print('PASS: public worker HEVC input/output and scene cut', flush=True)
    finally:
        (root/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(root/'report.json', flush=True)


if __name__ == '__main__':
    main()
