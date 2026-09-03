from dataclasses import dataclass


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
