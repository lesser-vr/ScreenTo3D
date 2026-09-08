"""Local GPU app gate: preprocessing/parity/lifecycle/output preservation."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import uuid
from unittest.mock import patch
import tkinter as tk
import cv2
import numpy as np
import torch
from da2_base_experiment import Da2BaseOracle, ROOT
from depthsbs_app.da2_base import binding, preprocess
from depthsbs_app import pipeline
from depthsbs_app.resources import configure_media_tools
from depthsbs_app.gui import DepthSbsGui


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--engine-dir', type=Path, default=ROOT/'out/da2-base-local')
    args = parser.parse_args()
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    directory = args.engine_dir
    runtime = Path('C:/TensorRT/TensorRT-11.2.1.2/bin')
    configure_media_tools(ROOT/'out/gpu-preview/DepthSBS-GPU-Preview/_internal/ffmpeg')
    root = ROOT/'out/da2-base-app'/uuid.uuid4().hex
    root.mkdir(parents=True)
    report = dict(passed=False)
    backend = binding(directory, runtime)
    backend.input_validator(pipeline.probe_video(args.input))
    try:
        capture = cv2.VideoCapture(str(args.input))
        try:
            ok, bgr = capture.read()
            assert ok
        finally:
            capture.release()
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        with Da2BaseOracle() as oracle, backend.engine_factory(None) as engine:
            tensor, _ = oracle.model.image2tensor(bgr, 518)
            np.testing.assert_array_equal(preprocess(rgb, tuple(tensor.shape[-2:])), tensor.cpu().numpy()[0])
            expected, actual = oracle.infer(rgb), engine.infer(rgb)
            np.testing.assert_allclose(actual, expected, atol=.001, rtol=.001)
            report['max_abs'] = float(np.abs(actual-expected).max())
        engine.close()
        try:
            engine.infer(rgb)
        except RuntimeError:
            pass
        else:
            raise AssertionError('Use after close')
        sentinel = b'previous output must survive'
        for failure in (False, True):
            path = root/('failure.mp4' if failure else 'cancel.mp4')
            path.write_bytes(sentinel)
            cancel = root/'cancel.flag'
            current = backend
            if failure:
                def factory(progress):
                    owned = backend.engine_factory(progress)
                    original = owned.infer
                    def infer(frame):
                        if owned.calls == 3:
                            raise RuntimeError('injected DA2 failure')
                        return original(frame)
                    owned.infer = infer
                    return owned
                current = replace(backend, engine_factory=factory)
            def progress(event):
                if not failure and event.get('event') == 'progress' and event['frame'] >= 1:
                    cancel.touch()
            try:
                pipeline.convert_video(args.input, path, 'balanced', progress,
                    cancel if not failure else None, depth_backend=current)
            except (InterruptedError, RuntimeError) as error:
                if failure and 'injected DA2 failure' not in str(error):
                    raise
                if not failure and not isinstance(error, InterruptedError):
                    raise
            else:
                raise AssertionError('Expected failure/cancellation')
            assert path.read_bytes() == sentinel
        gui_root = tk.Tk()
        gui_root.withdraw()
        try:
            gui = DepthSbsGui(gui_root, backend='da2-base', engine_dir=directory, runtime_dir=runtime)
            gui.input_value.set(str(args.input))
            gui.output_value.set(str(root/'gui-not-created.mp4'))
            with patch('depthsbs_app.gui.subprocess.Popen') as spawn, patch('depthsbs_app.gui.threading.Thread.start'):
                gui.start()
                command = spawn.call_args.args[0]
                assert command[command.index('--depth-backend')+1] == 'da2-base'
                assert command[command.index('--da2-base-engine-dir')+1] == str(directory)
                gui.process = None
        finally:
            gui_root.destroy()
        report['passed'] = True
    finally:
        (root/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(root/'report.json')


if __name__ == '__main__':
    main()
