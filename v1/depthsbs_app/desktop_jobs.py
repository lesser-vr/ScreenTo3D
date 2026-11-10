"""GUI-independent job policy. No Qt, GPU imports or hidden substitutions."""

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
        "CC-BY-NC-4.0 · 비상업용",
    ),
    "vda-small": (
        "VDA Small",
        "vda-local",
        "--vda-engine-dir",
        "Apache-2.0 · 로컬 미리보기",
    ),
    "ovda-small-c16": (
        "oVDA c16",
        "ovda-local",
        "--ovda-engine-dir",
        "NC-SA-UHDV1.0 · 비상업용 / 재배포 조건 확인",
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
            raise ValueError("입체 출력 형식을 확인하세요.")
        source, output = Path(self.source), Path(self.output)
        if not source.is_file() or source.suffix.lower() not in VIDEO_SUFFIXES:
            raise ValueError("지원되는 로컬 영상 파일을 선택하세요.")
        if output.suffix.lower() != ".mp4" or not output.parent.is_dir():
            raise ValueError("존재하는 폴더의 MP4 저장 위치를 선택하세요.")
        if source.resolve() == output.resolve() or (
            output.exists() and os.path.samefile(source, output)
        ):
            raise ValueError("원본 파일에 덮어쓸 수 없습니다.")
        if (
            self.mode not in MODES
            or self.codec not in OUTPUTS
            or self.model not in MODELS
        ):
            raise ValueError("모드, 코덱 또는 모델 설정을 확인하세요.")
        validate_mode_model(self.mode, self.model)
        if self.renderer not in ("cpu", "cuda"):
            raise ValueError("렌더러 설정을 확인하세요.")
        if self.model in STATEFUL and MODES[self.mode].inference_cadence != 1:
            raise ValueError(
                "이 모델은 모든 프레임을 처리해야 합니다. Balanced 이상을 선택하세요."
            )
        if self.model == "ovda-small-c16" and not self.noncommercial:
            raise ValueError(
                "설정에서 oVDA 라이선스를 읽고 개인·비상업적 사용을 확인하세요."
            )
        if self.model != "da2-small" and not Path(self.engine).is_dir():
            raise ValueError("설정에서 선택한 모델의 설치 폴더를 확인하세요.")
        if not all(
            (Path(self.media) / (n + ".exe")).is_file() for n in ("ffmpeg", "ffprobe")
        ):
            raise ValueError("설정에서 영상 도구 설치 경로를 확인하세요.")
        if not (Path(self.runtime) / "nvinfer_11.dll").is_file():
            raise ValueError("설정에서 TensorRT 실행 환경을 확인하세요.")

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
            raise ValueError("다른 작업이 실행 중입니다. 먼저 해당 작업을 종료하세요.")
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
        "사용할 수 있는 출력 이름이 없습니다. 저장 위치를 직접 선택하세요."
    )
