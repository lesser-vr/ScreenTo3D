"""Real Tk, fake subprocess: no GPU needed, no media publication."""
from pathlib import Path
import tempfile
import tkinter as tk
from unittest.mock import patch
from depthsbs_app.gui import DepthSbsGui

ROOT = Path(__file__).resolve().parents[1]


def main():
    root = tk.Tk()
    root.withdraw()
    try:
        gui = DepthSbsGui(root, backend='ovda-small-c16', mode='video-quality',
                          engine_dir=ROOT/'out/ovda-local', runtime_dir=Path('C:/TensorRT/TensorRT-11.2.1.2/bin'), stereo_renderer='cuda')
        root.update_idletasks()
        panel = root.winfo_children()[0]
        assert panel.winfo_reqheight() <= 840, panel.winfo_reqheight()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'input.mp4'; source.touch()
            gui.input_value.set(str(source)); gui.output_value.set(str(Path(tmp)/'output.mp4'))
            with patch('depthsbs_app.gui.subprocess.Popen') as spawn, patch('depthsbs_app.gui.threading.Thread.start'), \
                    patch('depthsbs_app.gui.messagebox.showerror') as error:
                gui.start(); spawn.assert_not_called()
                assert 'non-commercial' in error.call_args.args[1]
                gui.ovda_noncommercial.set(True); error.reset_mock()
                gui.start(); error.assert_not_called()
                command = spawn.call_args.args[0]
                assert command[command.index('--depth-backend')+1] == 'ovda-small-c16'
                assert command[command.index('--ovda-engine-dir')+1] == str(ROOT/'out/ovda-local')
                assert '--ovda-noncommercial' in command
                assert command[command.index('--stereo-renderer')+1]=='cuda'
                gui.cancel_file = Path(tmp)/'cancel.flag'
                gui.cancel(); assert gui.cancel_file.is_file()
                gui.process = None; spawn.reset_mock()
                gui.mode_value.set('performance'); gui.start(); spawn.assert_not_called()
                assert 'every frame' in error.call_args.args[1]
                gui.mode_value.set('video-quality')
                spawn.side_effect=OSError('worker could not launch')
                gui.start()
                assert gui.process is None and str(gui.start_button['state'])=='normal'
                assert 'worker could not launch' in error.call_args.args[1]
        print('PASS oVDA GUI: layout, license confirmation, selection, worker arguments, cancel, mode rejection')
    finally:
        root.destroy()


if __name__ == '__main__': main()
