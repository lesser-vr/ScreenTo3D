"""Explicit live-only refinements; file policies are not mutated."""

from .messages import Message as M

from dataclasses import asdict, dataclass, replace
from .config import MODES


@dataclass(frozen=True)
class LivePolicy:
    mode: str
    guide_radius: int
    flat_refinement: bool
    description: str
    presentation_hz: int = 0

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
        from .live_model import model_adapter
        return dict(
            live=asdict(self),
            stereo=asdict(model_adapter(model).apply_live_policy(replace(self.resolve(strength), depth_backend=model))),
            model=model,
            depth_reuse_guard="exact_rgb_equality_on_noncadence_frames",
            resize=False,
            zero_copy=False,
        )


DA2_LIVE_GUIDE_RADIUS = 8

LIVE_MODES = {
    "performance": LivePolicy(
        "performance",
        DA2_LIVE_GUIDE_RADIUS,
        True,
        M('Lower processing cost · Reuse depth in static scenes'),
    ),
    "balanced": LivePolicy(
        "balanced", DA2_LIVE_GUIDE_RADIUS, True, M('Balanced default · Infer each processed frame · Background and edge refinement')
    ),
    "video-quality": LivePolicy(
        "video-quality",
        12,
        True,
        M('Stronger temporal stabilization · Infer each processed frame · Wider edge guide'),
    ),
}


def resolve_live(mode, strength=1.0):
    if mode not in LIVE_MODES:
        raise ValueError(
            M('Offline Quality is available for files only. Select a supported live mode.')
        )
    return LIVE_MODES[mode].resolve(strength)


def same_rgb(frame, previous):
    import numpy as np
    from .gpu_frame import GpuFrame
    return frame.same_pixels(previous) if isinstance(frame, GpuFrame) else np.array_equal(frame, previous)


class StaticSbsReuse:
    """Track one uninterrupted run of identical source pixels in a native session."""
    # motion_static_probe reports unsettled EMA, changed projection depth,
    # unsettled range, unsettled mask, and an unprimed comparison in bits 0–4.
    UNSETTLED_HISTORY = 1 | 4 | 8

    def __init__(self):
        self.repeats = 0
        self.probed = False
        self.valid_until = 0
        self.stationary = False

    def hold(self, same, source_ns):
        if not same:
            self.repeats = 0
            self.probed = False
            self.valid_until = 0
            self.stationary = False
            return False
        self.repeats += 1
        return source_ns < self.valid_until

    def after_render(self, projection, source_ns):
        # Avoid probing isolated duplicates (e.g. 24 Hz content at 60 Hz).
        # Once settled, revalidate with a real render once per source second.
        if self.repeats and (self.valid_until or self.repeats % 4 == 0):
            pending = projection.motion_history.static_probe(projection.handle, self.probed)
            projection.syncs += 1
            projection.d2h += 4
            self.probed = True
            # First settle the actual displayed range; then verify a completed
            # render using that stationary range before retaining the texture.
            self.valid_until = source_ns + 1_000_000_000 if self.stationary and pending == 0 else 0
            self.stationary = self.stationary or (pending & self.UNSETTLED_HISTORY) == 0


def refresh_live(frame, inferred_frame, index, policy, cut, same=None):
    """Conservative live reuse: changed pixels always request fresh depth.

    Avoid full floating-point/local-density motion analysis when the cheaper
    exact comparison already proves that live content changed.
    """
    if inferred_frame is None:
        return "initial"
    if cut:
        return "cut"
    if index % policy.inference_cadence == 0:
        return "cadence"
    if same is None:
        same = same_rgb(frame, inferred_frame)
    return "reuse" if same else "motion"
