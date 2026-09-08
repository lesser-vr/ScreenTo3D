"""Real Tk layout and mocked worker command test; creates no conversion process."""
import argparse
from pathlib import Path
import tkinter as tk
from unittest.mock import patch

from depthsbs_app.gui import DepthSbsGui
from vda_streaming_experiment import ROOT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--engine-dir', type=Path, default=ROOT/'out/vda-local')
    args = parser.parse_args()
    root = tk.Tk()
    root.withdraw()
    try:
        gui = DepthSbsGui(root, backend='vda-small', mode='video-quality',
            engine_dir=args.engine_dir,
            runtime_dir=Path('C:/TensorRT/TensorRT-11.2.1.2/bin'),
            media_tools=ROOT/'out/gpu-preview/DepthSBS-GPU-Preview/_internal/ffmpeg')
        root.update_idletasks()
        gui.input_value.set(str(args.input))
        gui.output_value.set(str(ROOT/'out/vda-gui-test-not-created.mp4'))
        with patch('depthsbs_app.gui.subprocess.Popen') as spawn, patch('depthsbs_app.gui.threading.Thread.start'), \
                patch('depthsbs_app.gui.messagebox.showerror') as error:
            gui.start()
            error.assert_not_called()
            assert gui.refinement_value.get() == ''
            gui._event(dict(event='start', metadata=dict(width=1056, height=608)))
            assert '2112 x 608' in gui.geometry_value.get()
            gui._event(dict(event='complete', processing_fps=1, telemetry=dict(stereo=dict(
                letterbox=dict(enabled=True, applied_frames=0, warmup_frames=0, bypassed_frames=124)))))
            assert '0 frames applied' in gui.refinement_value.get()
            assert '124 bypassed' in gui.refinement_value.get()
            command = spawn.call_args.args[0]
            assert '--letterbox-refinement' not in command
            for flag, expected in (('--depth-backend', 'vda-small'), ('--mode', 'video-quality'),
                                   ('--vda-engine-dir', gui.engine_value.get()), ('--runtime-dir', str(gui.runtime_dir))):
                assert command[command.index(flag)+1] == expected
            gui.process = None
            gui.letterbox_value.set(True)
            spawn.reset_mock()
            gui.start()
            assert '--letterbox-refinement' in spawn.call_args.args[0]
            assert gui.refinement_value.get() == ''
            assert gui.geometry_value.get() == 'Reading input dimensions...'
            gui._event(dict(event='complete', processing_fps=1))
            assert 'not reported' in gui.refinement_value.get()
            gui.process = None
            gui.mode_value.set('performance')
            spawn.reset_mock()
            gui.start()
            spawn.assert_not_called()
            assert 'every frame' in error.call_args.args[1]
        print('PASS: VDA GUI construction, worker arguments and incompatible-mode rejection')
    finally:
        root.destroy()
    root = tk.Tk()
    root.withdraw()
    try:
        gui = DepthSbsGui(root)
        assert gui.backend_value.get() == 'da2-small' and gui.mode_value.get() == 'balanced'
        assert not gui.letterbox_value.get()
        print('PASS: DA2 GUI defaults unchanged')
    finally:
        root.destroy()


if __name__ == '__main__':
    main()
