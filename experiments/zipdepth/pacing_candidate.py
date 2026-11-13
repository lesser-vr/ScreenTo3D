"""Explicit benchmark-only cadence candidates; never imported by application launch."""
import os

from screento3d_app.presentation_policy import PresentationCadence


class PhaseCadence(PresentationCadence):
    """Recover small scheduling jitter without accumulating it or bursting.

    This intentionally changes strict minimum spacing: recovery is at most 2ms.
    Larger delays reset phase, and there is always one future deadline.
    """
    jitter_ns = 2_000_000

    def emitted(self, now):
        jitter = min(self.jitter_ns, self.period_ns // 4)
        if self.period_ns and self.next_ns and 0 <= now - self.next_ns <= jitter:
            self.next_ns += self.period_ns
        else:
            self.next_ns = now + self.period_ns


class Phase3Cadence(PhaseCadence):
    jitter_ns = 3_000_000


CANDIDATES = {'phase': PhaseCadence, 'phase3': Phase3Cadence}


class ImmediateDelivery(PresentationCadence):
    """Non-VFG native trial: worker owns rate, consumer publishes ready results.

    Preserve hz/period metadata so work receives the requested cap and the
    consumer still consumes at most one descriptor per poll. Output spacing is
    intentionally no longer a separate strict limiter.
    """
    def ready(self, now):
        return True


class GuardedDelivery(PresentationCadence):
    """Keep result jitter from causing closely spaced broker publications."""
    def emitted(self, now):
        guard = self.period_ns - min(3_000_000, self.period_ns // 4)
        self.next_ns = now + guard


DELIVERY = dict(CANDIDATES, **{'relative': PresentationCadence, 'work-phase3': ImmediateDelivery, 'work-guard3': GuardedDelivery})
WORK = dict(CANDIDATES, **{'relative': PresentationCadence, 'work-phase3': Phase3Cadence, 'work-guard3': Phase3Cadence})


def polling_wakeup_type():
    from PySide6.QtCore import QObject, Signal

    class PollingWakeup(QObject):
        ready = Signal()
        failed = Signal(str)
        writer = None
        health_interval_ms = 1
        event_driven = False

        def close(self):
            pass

    return PollingWakeup


from screento3d_app.environment import get as app_env, required as app_env_required

def worker(*args, **kwargs):
    from screento3d_app import presentation_policy
    presentation_policy.WorkCadence = WORK[app_env_required('SCREENTO3D_PACING_CANDIDATE')]
    if app_env('SCREENTO3D_PACING_TRACE') == '1':
        from pacing_probe import worker as target
    elif app_env_required('SCREENTO3D_PACING_MODEL') == 'zipdepth':
        from trial import worker as target
    else:
        from screento3d_app.live_sbs import sbs_worker as target
    return target(*args, **kwargs)
