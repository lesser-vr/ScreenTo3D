"""Explicit live-only refinements; file policies are not mutated."""

from dataclasses import asdict, dataclass, replace
from .config import MODES


@dataclass(frozen=True)
class LivePolicy:
    mode: str
    guide_radius: int
    flat_refinement: bool
    description: str
    presentation_hz: int = 30

    def resolve(self, strength=1.0):
        if not 0.25 <= strength <= 2.0:
            raise ValueError("Invalid live strength")
        base = MODES[self.mode]
        return replace(
            base,
            divergence=base.divergence * strength,
            depth_guide_radius=self.guide_radius,
            flat_background_refinement=self.flat_refinement,
            temporal_depth_transition=0.008,
        )

    def describe(self, strength=1.0, model="da2-small"):
        return dict(
            live=asdict(self),
            stereo=asdict(replace(self.resolve(strength), depth_backend=model)),
            model=model,
            depth_reuse_guard="exact_rgb_equality_on_noncadence_frames",
            resize=False,
            zero_copy=False,
        )


LIVE_MODES = {
    "performance": LivePolicy(
        "performance",
        4,
        False,
        "낮은 처리 비용 · 배경 보정 생략 · 정적인 장면에서 깊이 재사용",
    ),
    "balanced": LivePolicy(
        "balanced", 8, True, "기본 균형 · 매 처리 프레임 추론 · 배경/경계 보정"
    ),
    "video-quality": LivePolicy(
        "video-quality",
        12,
        True,
        "강한 시간 안정화 · 매 처리 프레임 추론 · 넓은 경계 가이드",
    ),
}


def resolve_live(mode, strength=1.0):
    if mode not in LIVE_MODES:
        raise ValueError(
            "Offline Quality는 파일 전용입니다. 지원되는 실시간 모드를 선택하세요."
        )
    return LIVE_MODES[mode].resolve(strength)


def refresh_live(frame, inferred_frame, index, policy, cut):
    """Conservative live reuse: changed pixels always request fresh depth.

    Avoid full floating-point/local-density motion analysis when the cheaper
    exact comparison already proves that live content changed.
    """
    import numpy as np

    if inferred_frame is None:
        return "initial"
    if cut:
        return "cut"
    if index % policy.inference_cadence == 0:
        return "cadence"
    return "reuse" if np.array_equal(frame, inferred_frame) else "motion"
