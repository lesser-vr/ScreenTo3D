import json
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .config import MODES, OUTPUTS


class ScreenTo3DGui:
    def __init__(self, root: tk.Tk, gpu_preview=False, backend='da2-small', engine_dir=None,
                 runtime_dir=None, media_tools=None, mode='balanced', letterbox_refinement=False, stereo_renderer=None):
        self.gpu_preview = gpu_preview
        self.runtime_dir, self.media_tools = runtime_dir, media_tools
        self.root, self.process = root, None
        self.status_file = self.cancel_file = None
        root.title("ScreenTo3D GPU Preview (experimental)" if gpu_preview else "ScreenTo3D v1")
        root.geometry("740x840")
        root.minsize(660, 830)
        self.input_value, self.output_value = tk.StringVar(), tk.StringVar()
        self.mode_value = tk.StringVar(value=mode)
        self.backend_value = tk.StringVar(value=backend)
        self.engine_value = tk.StringVar(value=str(engine_dir) if engine_dir else '')
        self.codec_value = tk.StringVar(value='h264')
        self.letterbox_value = tk.BooleanVar(value=letterbox_refinement)
        self.ovda_noncommercial = tk.BooleanVar(value=False)
        self.stereo_value = tk.StringVar(value=stereo_renderer or 'cpu')
        self.geometry_value = tk.StringVar(value='Output: Full SBS; each eye keeps the input dimensions.')
        self.refinement_value = tk.StringVar(value='')
        self.status_value, self.progress_value = tk.StringVar(value="Ready"), tk.DoubleVar(value=0.0)
        self._build()
        root.protocol("WM_DELETE_WINDOW", self.close)

    def _build(self):
        panel = ttk.Frame(self.root, padding=20)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text="ScreenTo3D", font=("Segoe UI", 20, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 16))
        ttk.Label(panel, text="Input video").grid(row=1, column=0, sticky="w")
        ttk.Entry(panel, textvariable=self.input_value).grid(row=2, column=0, columnspan=2, sticky="ew")
        ttk.Button(panel, text="Browse", command=self.choose_input).grid(row=2, column=2, padx=(8, 0))
        ttk.Label(panel, text="Output MP4").grid(row=3, column=0, sticky="w", pady=(14, 0))
        ttk.Entry(panel, textvariable=self.output_value).grid(row=4, column=0, columnspan=2, sticky="ew")
        ttk.Button(panel, text="Browse", command=self.choose_output).grid(row=4, column=2, padx=(8, 0))
        ttk.Label(panel, text="Mode").grid(row=5, column=0, sticky="w", pady=(14, 0))
        mode_box = ttk.Combobox(panel, textvariable=self.mode_value, state="readonly", values=tuple(MODES))
        mode_box.grid(row=6, column=0, columnspan=2, sticky="ew")
        ttk.Label(panel, text='Output codec (HEVC for 4K; compatible player required)').grid(row=7, column=0, columnspan=3, sticky='w', pady=(12, 0))
        ttk.Combobox(panel, textvariable=self.codec_value, state='readonly', values=tuple(OUTPUTS)).grid(row=8, column=0, columnspan=2, sticky='ew')
        ttk.Label(panel, text='Depth model (Offline Quality: VDA centered 5-frame processing)').grid(row=9, column=0, columnspan=3, sticky='w', pady=(12, 0))
        ttk.Combobox(panel, textvariable=self.backend_value, state='readonly', values=('da2-small', 'da2-base', 'vda-small', 'ovda-small-c16')).grid(row=10, column=0, columnspan=2, sticky='ew')
        ttk.Label(panel, text='Selected model engine folder (DA2 Base: non-commercial use)').grid(row=11, column=0, columnspan=3, sticky='w', pady=(12, 0))
        ttk.Entry(panel, textvariable=self.engine_value).grid(row=12, column=0, columnspan=2, sticky='ew')
        ttk.Button(panel, text='Browse', command=self.choose_engine).grid(row=12, column=2, padx=(8, 0))
        ttk.Progressbar(panel, variable=self.progress_value, maximum=100).grid(row=13, column=0, columnspan=3, sticky="ew", pady=(20, 6))
        ttk.Label(panel, textvariable=self.status_value).grid(row=14, column=0, columnspan=3, sticky="w")
        self.start_button = ttk.Button(panel, text="Convert", command=self.start)
        self.start_button.grid(row=15, column=1, sticky="e", pady=(18, 0))
        self.cancel_button = ttk.Button(panel, text="Cancel", command=self.cancel, state="disabled")
        self.cancel_button.grid(row=15, column=2, sticky="e", padx=(8, 0), pady=(18, 0))
        ttk.Checkbutton(panel, text='Experimental: refine flat backdrops inside black bars',
                        variable=self.letterbox_value).grid(row=16, column=0, columnspan=3, sticky='w', pady=(12, 0))
        ttk.Label(panel, text='Does not add or remove black bars already in the input.',
                  wraplength=590).grid(row=17, column=0, columnspan=3, sticky='w')
        ttk.Label(panel, textvariable=self.geometry_value, wraplength=590).grid(
            row=18, column=0, columnspan=3, sticky='w', pady=(8, 0))
        ttk.Label(panel, textvariable=self.refinement_value, wraplength=590).grid(
            row=19, column=0, columnspan=3, sticky='w')
        ttk.Checkbutton(panel, text='oVDA only: I confirm personal/non-commercial use (NC-SA-UHDV1.0)',
                        variable=self.ovda_noncommercial).grid(row=20, column=0, columnspan=3, sticky='w', pady=(8, 0))
        ttk.Label(panel, text='oVDA: read experiments/ovda/LICENSE; redistribution/share-alike conditions apply.',
                  wraplength=590).grid(row=21, column=0, columnspan=3, sticky='w')
        if not self.gpu_preview:
            ttk.Label(panel, text='Stereo processing (CUDA: validated local GPU; no automatic fallback)').grid(row=22, column=0, columnspan=3, sticky='w', pady=(8, 0))
            ttk.Combobox(panel, textvariable=self.stereo_value, state='readonly', values=('cpu', 'cuda')).grid(row=23, column=0, columnspan=2, sticky='ew')
            ttk.Button(panel, text='Check oVDA setup', command=self.check_ovda_setup).grid(row=23, column=2, padx=(8, 0))
        panel.columnconfigure(0, weight=1)
        panel.columnconfigure(1, weight=1)

    def choose_input(self):
        value = filedialog.askopenfilename(title="Select video", filetypes=[("Video files", "*.mp4 *.mkv *.mov *.m4v"), ("All files", "*.*")])
        if value:
            self.input_value.set(value)
            source = Path(value)
            self.output_value.set(str(source.with_name(source.stem + "_SBS.mp4")))

    def check_ovda_setup(self):
        if self.process is not None:
            messagebox.showinfo('ScreenTo3D', 'Wait for the active conversion to finish before checking setup.')
            return
        from .ovda_installation import installation_report, summary
        report = installation_report(Path(self.engine_value.get()), self.runtime_dir, self.media_tools, self.stereo_value.get())
        show = messagebox.showinfo if report['ready'] else messagebox.showerror
        show('oVDA setup: '+('ready' if report['ready'] else 'needs attention'), summary(report))

    def choose_output(self):
        value = filedialog.asksaveasfilename(title="Save SBS video", defaultextension=".mp4", filetypes=[("MP4 video", "*.mp4")])
        if value:
            self.output_value.set(value)

    def choose_engine(self):
        value = filedialog.askdirectory(title='Select trusted model engine folder')
        if value:
            self.engine_value.set(value)

    def start(self):
        source, destination = Path(self.input_value.get()), Path(self.output_value.get())
        if not source.is_file():
            messagebox.showerror("ScreenTo3D", "Select a valid input video.")
            return
        if destination.suffix.lower() != ".mp4":
            messagebox.showerror("ScreenTo3D", "Select an MP4 output path.")
            return
        if self.backend_value.get() == 'ovda-small-c16':
            try:
                from .ovda import binding
                binding(Path(self.engine_value.get()), self.runtime_dir,
                        self.ovda_noncommercial.get()).validate_policy(MODES[self.mode_value.get()])
            except Exception as error:
                messagebox.showerror('ScreenTo3D oVDA', str(error))
                return
        if self.backend_value.get() == 'vda-small':
            try:
                from .depth_backend import vda_binding, vda_offline_binding
                create_binding = vda_offline_binding if self.mode_value.get() == 'offline-quality' else vda_binding
                create_binding(Path(self.engine_value.get()), self.runtime_dir).validate_policy(MODES[self.mode_value.get()])
            except Exception as error:
                messagebox.showerror('ScreenTo3D VDA', str(error))
                return
        self.start_button.configure(state="disabled")
        if self.backend_value.get() == 'da2-base':
            try:
                from .da2_base import binding
                binding(Path(self.engine_value.get()), self.runtime_dir)
            except Exception as error:
                self.start_button.configure(state='normal')
                messagebox.showerror('ScreenTo3D DA2 Base', str(error))
                return
        self.cancel_button.configure(state="normal")
        self.progress_value.set(0)
        self.status_value.set("Starting...")
        self.geometry_value.set('Reading input dimensions...')
        self.refinement_value.set('')
        token = f"screento3d-{time.time_ns()}"
        from .user_data import prepare_environment
        folder=prepare_environment()/'temp'
        self.status_file = folder / f"{token}.jsonl"
        self.cancel_file = folder / f"{token}.cancel"
        arguments = [
            "--worker", "--input", str(source), "--output", str(destination),
            "--mode", self.mode_value.get(), "--status-file", str(self.status_file),
            "--cancel-file", str(self.cancel_file),
            '--output-codec', self.codec_value.get(),
            '--depth-backend', self.backend_value.get(),
        ]
        if self.backend_value.get() == 'vda-small':
            arguments += ['--vda-engine-dir', self.engine_value.get()]
        if self.backend_value.get() == 'da2-base':
            arguments += ['--da2-base-engine-dir', self.engine_value.get()]
        if self.backend_value.get() == 'ovda-small-c16':
            arguments += ['--ovda-engine-dir', self.engine_value.get(), '--ovda-noncommercial']
        if self.letterbox_value.get():
            arguments += ['--letterbox-refinement']
        if not self.gpu_preview:
            arguments += ['--stereo-renderer', self.stereo_value.get()]
        for flag, value in (('--runtime-dir', self.runtime_dir), ('--media-tools', self.media_tools)):
            if value is not None:
                arguments += [flag, str(value)]
        module = 'screento3d_gpu_preview' if self.gpu_preview else 'screento3d_app.main'
        command = [sys.executable, *arguments] if getattr(sys, "frozen", False) else [sys.executable, "-m", module, *arguments]
        try:
            self.process = subprocess.Popen(command, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        except OSError as error:
            self.process = None
            self.start_button.configure(state='normal')
            self.cancel_button.configure(state='disabled')
            self.status_value.set('Could not start conversion')
            messagebox.showerror('ScreenTo3D', str(error))
            return
        threading.Thread(target=self._watch_worker, daemon=True).start()

    def _watch_worker(self):
        position = 0
        while self.process is not None and self.process.poll() is None:
            position = self._read_events(position)
            time.sleep(0.15)
        position = self._read_events(position)
        return_code = self.process.returncode if self.process is not None else 2
        self.root.after(0, self._finished, return_code)

    def _read_events(self, position: int) -> int:
        if self.status_file is None or not self.status_file.exists():
            return position
        with self.status_file.open("r", encoding="utf-8") as source:
            source.seek(position)
            for line in source:
                try:
                    self.root.after(0, self._event, json.loads(line))
                except json.JSONDecodeError:
                    pass
            return source.tell()

    def _event(self, event: dict):
        kind = event.get("event")
        if kind == 'start':
            metadata = event.get('metadata', {})
            width, height = metadata.get('width'), metadata.get('height')
            if type(width) is int and type(height) is int and width > 0 and height > 0:
                self.geometry_value.set(f'Input / each eye: {width} x {height} | Full SBS: {width*2} x {height}')
        elif kind == "engine_build":
            self.status_value.set("Optimizing the depth engine for this GPU (first run)...")
        elif kind == "progress":
            if event.get("percent") is not None:
                self.progress_value.set(event["percent"])
                self.status_value.set(f"Converting frame {event['frame']} / {event['total_frames']}")
            else:
                self.status_value.set(f"Converting frame {event['frame']}")
        elif kind == "complete":
            self.progress_value.set(100)
            self.status_value.set(f"Complete — {event['processing_fps']:.1f} fps")
            padding = event.get('telemetry', {}).get('stereo', {}).get('letterbox', {})
            if padding.get('enabled'):
                self.refinement_value.set(
                    f"Black-bar backdrop refinement: {padding.get('applied_frames', 0)} frames applied; "
                    f"{padding.get('warmup_frames', 0)} confirming; {padding.get('bypassed_frames', 0)} bypassed. "
                    'Bypass leaves normal refinement unchanged.')
            else:
                self.refinement_value.set('Black-bar backdrop refinement: off / not reported.')
        elif kind == "cancelled":
            self.status_value.set("Cancelled")
        elif kind == "error" and not self.status_value.get().startswith("Cancelling"):
            self.status_value.set("Conversion failed")
            messagebox.showerror("ScreenTo3D", event.get("message", "Unknown conversion error"))

    def _finished(self, return_code: int):
        self.process = None
        self.start_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        if return_code == 0:
            messagebox.showinfo("ScreenTo3D", "Conversion complete.")
        elif return_code == 2:
            self.status_value.set("Cancelled")
        for path in (self.status_file, self.cancel_file):
            if path is not None:
                path.unlink(missing_ok=True)

    def cancel(self):
        if self.process is not None and self.cancel_file is not None:
            self.cancel_file.write_text("cancel", encoding="ascii")
            self.status_value.set("Cancelling...")
            self.cancel_button.configure(state="disabled")

    def close(self):
        self.cancel()
        self.root.destroy()


def run_gui(gpu_preview=False, **options) -> None:
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    ScreenTo3DGui(root, gpu_preview=gpu_preview, **options)
    root.mainloop()
