from dataclasses import dataclass


@dataclass(frozen=True)
class OutputPolicy:
    name: str
    encoder: str
    tag: str
    max_sbs_width: int


OUTPUTS = {
    'h264': OutputPolicy('H.264', 'h264_nvenc', 'avc1', 4096),
    'hevc': OutputPolicy('HEVC', 'hevc_nvenc', 'hvc1', 8192),
}


@dataclass(frozen=True)
class ModePolicy:
    name: str
    label: str
    inference_cadence: int
    temporal_alpha: float
    divergence: float
    convergence: float
    nvenc_preset: str
    cq: int
    depth_backend: str = 'da2-small'
    temporal_color_threshold: float = 0.04
    temporal_depth_threshold: float = 0.08
    scene_cut_threshold: float = 0.18
    depth_guide_radius: int = 8
    flat_background_refinement: bool = True
    flat_background_tolerance: float = 0.04
    flat_background_min_coverage: float = 0.35
    conservative_stereo_coverage: bool = True
    motion_refresh_fraction: float = 0.01
    motion_refresh_color_threshold: float = 0.04
    local_motion_window: int = 16
    local_motion_fraction: float = 0.0625
    local_motion_color_threshold: float = 0.02
    local_motion_concentration: float = 3.0
    letterbox_refinement: bool = False
    letterbox_stable_frames: int = 3
    temporal_depth_transition: float = 0.0


MODES = {
    "performance": ModePolicy(
        "performance", "Performance", 2, 0.55, 0.018, 0.45, "p3", 25
    ),
    "balanced": ModePolicy(
        "balanced", "Balanced", 1, 0.35, 0.026, 0.45, "p4", 22
    ),
    "video-quality": ModePolicy(
        "video-quality", "Video Quality", 1, 0.18, 0.030, 0.45, "p6", 19
    ),
    "offline-quality": ModePolicy(
        "offline-quality", "Offline Quality", 1, 0.12, 0.038, 0.43, "p7", 17
    ),
}


# Product modes own their model identity. Multiple entries mean an explicit
# choice within that mode, never permission to select an unrelated fallback.
MODE_MODEL_CHOICES = {
    "performance": ("da2-small",),
    "balanced": ("da2-base",),
    "video-quality": ("ovda-small-c16", "vda-small"),
    # DA3 Mono may be added after a validated backend exists. VDA Small is paired
    # with the dedicated bounded centered-window processor for file-only Offline.
    "offline-quality": ("vda-small",),
}

DEFAULT_MODE_MODELS = {
    "performance": "da2-small",
    "balanced": "da2-base",
    "video-quality": "vda-small",
    "offline-quality": "vda-small",
}


def validate_mode_model(mode, model):
    if mode not in MODES or model not in MODE_MODEL_CHOICES.get(mode, ()):
        raise ValueError("선택한 처리 모드와 깊이 모델이 일치하지 않습니다.")
    return model
