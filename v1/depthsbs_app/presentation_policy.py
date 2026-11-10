"""Deadline pacing; polling observes latest frames, never queues frame history."""


class PresentationCadence:
    def __init__(self, hz=0):
        if type(hz) is not int or hz not in (0, 30, 60):
            raise ValueError("Supported output limits are unlimited (0), 30 and 60 FPS")
        self.hz = hz
        self.period_ns = round(1_000_000_000 / hz) if hz else 0
        self.next_ns = 0

    @property
    def poll_ms(self):
        return 1

    def ready(self, now):
        return now >= self.next_ns

    def emitted(self, now):
        # A late poll must not be followed by a shortened catch-up interval.
        self.next_ns = now + self.period_ns

    def wait_seconds(self, now):
        return .001


class WorkCadence(PresentationCadence):
    """One work-rate owner; recover bounded jitter, never replay missed work."""
    def emitted(self, now):
        jitter = min(3_000_000, self.period_ns // 4)
        if self.period_ns and self.next_ns and 0 <= now - self.next_ns <= jitter:
            self.next_ns += self.period_ns
        else:
            self.next_ns = now + self.period_ns

    def wait_seconds(self, now):
        # Deadline waits are interrupted by stop. Once due, a blocked texture
        # slot still needs bounded GPU-ack polling, not a busy loop.
        remaining = (self.next_ns - now) / 1e9
        return min(remaining, .05) if remaining > 0 else .001


class NativeDeliveryCadence(PresentationCadence):
    """Short spacing guard; the non-VFG native worker owns the target rate."""
    def emitted(self, now):
        self.next_ns = now + self.period_ns - min(3_000_000, self.period_ns // 4)


def delivery_cadence(hz, *, native, vfg):
    return (NativeDeliveryCadence if native and not vfg else PresentationCadence)(hz)
