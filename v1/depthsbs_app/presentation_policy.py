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
