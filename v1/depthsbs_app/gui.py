import json
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .config import MODES


class DepthSbsGui:
    def __init__(self, root: tk.Tk):
        self.root, self.process = root, None
        self.status_file = self.cancel_file = None
        root.title("DepthSBS v1")
        root.geometry("680x360")
        root.minsize(620, 330)
        self.input_value, self.output_value = tk.StringVar(), tk.StringVar()
        self.mode_value = tk.StringVar(value="balanced")
        self.status_value, self.progress_value = tk.StringVar(value="Ready"), tk.DoubleVar(value=0.0)
        self._build()
        root.protocol("WM_DELETE_WINDOW", self.close)

    def _build(self):
        panel = ttk.Frame(self.root, padding=20)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text="DepthSBS", font=("Segoe UI", 20, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 16))
        ttk.Label(panel, text="Input video").grid(row=1, column=0, sticky="w")
        ttk.Entry(panel, textvariable=self.input_value).grid(row=2, column=0, columnspan=2, sticky="ew")
        ttk.Button(panel, text="Browse", command=self.choose_input).grid(row=2, column=2, padx=(8, 0))
        ttk.Label(panel, text="Output MP4").grid(row=3, column=0, sticky="w", pady=(14, 0))
        ttk.Entry(panel, textvariable=self.output_value).grid(row=4, column=0, columnspan=2, sticky="ew")
        ttk.Button(panel, text="Browse", command=self.choose_output).grid(row=4, column=2, padx=(8, 0))
        ttk.Label(panel, text="Mode").grid(row=5, column=0, sticky="w", pady=(14, 0))
        mode_box = ttk.Combobox(panel, textvariable=self.mode_value, state="readonly", values=tuple(MODES))
        mode_box.grid(row=6, column=0, columnspan=2, sticky="ew")
        ttk.Progressbar(panel, variable=self.progress_value, maximum=100).grid(row=7, column=0, columnspan=3, sticky="ew", pady=(20, 6))
        ttk.Label(panel, textvariable=self.status_value).grid(row=8, column=0, columnspan=3, sticky="w")
        self.start_button = ttk.Button(panel, text="Convert", command=self.start)
        self.start_button.grid(row=9, column=1, sticky="e", pady=(18, 0))
        self.cancel_button = ttk.Button(panel, text="Cancel", command=self.cancel, state="disabled")
        self.cancel_button.grid(row=9, column=2, sticky="e", padx=(8, 0), pady=(18, 0))
        panel.columnconfigure(0, weight=1)
        panel.columnconfigure(1, weight=1)

    def choose_input(self):
        value = filedialog.askopenfilename(title="Select video", filetypes=[("Video files", "*.mp4 *.mkv *.mov *.m4v"), ("All files", "*.*")])
        if value:
            self.input_value.set(value)
            source = Path(value)
            self.output_value.set(str(source.with_name(source.stem + "_SBS.mp4")))

    def choose_output(self):
        value = filedialog.asksaveasfilename(title="Save SBS video", defaultextension=".mp4", filetypes=[("MP4 video", "*.mp4")])
        if value:
            self.output_value.set(value)

    def start(self):
        source, destination = Path(self.input_value.get()), Path(self.output_value.get())
        if not source.is_file():
            messagebox.showerror("DepthSBS", "Select a valid input video.")
            return
        if destination.suffix.lower() != ".mp4":
            messagebox.showerror("DepthSBS", "Select an MP4 output path.")
            return
        self.start_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.progress_value.set(0)
        self.status_value.set("Starting...")
        token = f"depthsbs-{time.time_ns()}"
        self.status_file = Path(tempfile.gettempdir()) / f"{token}.jsonl"
        self.cancel_file = Path(tempfile.gettempdir()) / f"{token}.cancel"
        arguments = [
            "--worker", "--input", str(source), "--output", str(destination),
            "--mode", self.mode_value.get(), "--status-file", str(self.status_file),
            "--cancel-file", str(self.cancel_file),
        ]
        command = [sys.executable, *arguments] if getattr(sys, "frozen", False) else [sys.executable, "-m", "depthsbs_app.main", *arguments]
        self.process = subprocess.Popen(command, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
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
        if kind == "engine_build":
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
        elif kind == "cancelled":
            self.status_value.set("Cancelled")
        elif kind == "error" and not self.status_value.get().startswith("Cancelling"):
            self.status_value.set("Conversion failed")
            messagebox.showerror("DepthSBS", event.get("message", "Unknown conversion error"))

    def _finished(self, return_code: int):
        self.process = None
        self.start_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        if return_code == 0:
            messagebox.showinfo("DepthSBS", "Conversion complete.")
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


def run_gui() -> None:
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    DepthSbsGui(root)
    root.mainloop()
