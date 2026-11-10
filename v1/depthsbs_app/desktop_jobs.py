"""GUI-independent job policy. No Qt, GPU imports or hidden substitutions."""
from .messages import ErrorMessage as E

from .messages import Message as M

from dataclasses import dataclass
from pathlib import Path
import os

from .config import MODES, OUTPUTS, validate_mode_model

ROOT = Path(__file__).resolve().parents[2]
PORTABLE_DESKTOP = (ROOT / "desktop-portable").is_file()
BUNDLE = ROOT / "out/gpu-preview/DepthSBS-GPU-Preview/_internal"
MODELS = {
    "da2-small": ("DA2 Small", "", "", "Apache-2.0 · DA2 Small"),
    "da2-base": (
        "DA2 Base",
        "da2-base-local",
        "--da2-base-engine-dir",
        M('CC-BY-NC-4.0 · Non-commercial use'),
    ),
    "vda-small": (
        "VDA Small",
        "vda-local",
        "--vda-engine-dir",
        M('Apache-2.0 · Local preview'),
    ),
    "ovda-small-c16": (
        "oVDA c16",
        "ovda-local",
        "--ovda-engine-dir",
        M('NC-SA-UHDV1.0 · Non-commercial use / Check redistribution terms'),
    ),
}
STATEFUL = frozenset(("vda-small", "ovda-small-c16"))
VIDEO_SUFFIXES = frozenset((".mp4", ".mkv", ".mov", ".m4v"))


@dataclass(frozen=True)
class Job:
    source: str
    output: str
    mode: str
    codec: str
    model: str
    renderer: str
    engine: str
    runtime: str
    media: str
    noncommercial: bool = False
    letterbox: bool = False
    stereo_layout: str = "full-sbs"

    def validate(self):
        from .stereo_layout import LAYOUTS
        if self.stereo_layout not in LAYOUTS:
            raise ValueError(E('E_OUTPUT_LAYOUT_INVALID'))
        source, output = Path(self.source), Path(self.output)
        if not source.is_file() or source.suffix.lower() not in VIDEO_SUFFIXES:
            raise ValueError(E('E_FILE_INPUT_UNSUPPORTED'))
        if output.suffix.lower() != ".mp4" or not output.parent.is_dir():
            raise ValueError(E('E_OUTPUT_PATH_INVALID'))
        if source.resolve() == output.resolve() or (
            output.exists() and os.path.samefile(source, output)
        ):
            raise ValueError(E('E_OUTPUT_SOURCE_COLLISION'))
        if (
            self.mode not in MODES
            or self.codec not in OUTPUTS
            or self.model not in MODELS
        ):
            raise ValueError(E('E_FILE_OPTIONS_INVALID'))
        validate_mode_model(self.mode, self.model)
        if self.renderer not in ("cpu", "cuda"):
            raise ValueError(E('E_RENDERER_INVALID'))
        if self.model in STATEFUL and MODES[self.mode].inference_cadence != 1:
            raise ValueError(
                E('E_MODEL_FRAME_POLICY')
            )
        if self.model == "ovda-small-c16" and not self.noncommercial:
            raise ValueError(
                E('E_OVDA_LICENSE_REQUIRED')
            )
        if self.model != "da2-small" and not Path(self.engine).is_dir():
            raise ValueError(E('E_MODEL_PATH_INVALID'))
        if not all(
            (Path(self.media) / (n + ".exe")).is_file() for n in ("ffmpeg", "ffprobe")
        ):
            raise ValueError(E('E_MEDIA_TOOLS_INVALID'))
        if not (Path(self.runtime) / "nvinfer_11.dll").is_file():
            raise ValueError(E('E_TENSORRT_PATH_INVALID'))

    def arguments(self, cancel_file):
        args = [
            "--worker",
            "--input",
            self.source,
            "--output",
            self.output,
            "--mode",
            self.mode,
            "--output-codec",
            self.codec,
            "--stereo-layout",
            self.stereo_layout,
            "--depth-backend",
            self.model,
            "--stereo-renderer",
            self.renderer,
            "--runtime-dir",
            self.runtime,
            "--media-tools",
            self.media,
            "--cancel-file",
            str(cancel_file),
        ]
        flag = MODELS[self.model][2]
        if flag:
            args += [flag, self.engine]
        if self.noncommercial and self.model == "ovda-small-c16":
            args += ["--ovda-noncommercial"]
        if self.letterbox:
            args += ["--letterbox-refinement"]
        return args


class ProcessingLease:
    """One application-wide owner, including future live workers."""

    def __init__(self):
        self.owner = None

    def acquire(self, owner):
        if self.owner is not None:
            raise ValueError(E('E_TASK_BUSY'))
        self.owner = owner

    def release(self, owner):
        if self.owner != owner:
            raise ValueError("Processing lease owner mismatch")
        self.owner = None


def unused_output(source, reserved=()):
    source = Path(source)
    reserved = {str(Path(p).resolve()).casefold() for p in reserved}
    for index in range(10000):
        suffix = "" if index == 0 else f"_{index}"
        target = source.with_name(source.stem + "_SBS" + suffix + ".mp4")
        if not target.exists() and str(target.resolve()).casefold() not in reserved:
            return str(target)
    raise ValueError(
        E('E_OUTPUT_NAME_UNAVAILABLE')
    )
