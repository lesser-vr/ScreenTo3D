"""Deadline pacing; polling observes latest frames, never queues frame history."""


class PresentationCadence:
    def __init__(self, hz=30):
        if hz not in (30, 60):
            raise ValueError("Supported presentation targets are 30 and 60 Hz")
        self.hz = hz
        self.period_ns = round(1_000_000_000 / hz)
        self.next_ns = 0

    @property
    def poll_ms(self):
        return 4 if self.hz == 60 else 8

    def ready(self, now):
        return now >= self.next_ns

    def emitted(self, now):
        self.next_ns += self.period_ns
        if self.next_ns <= now:
            self.next_ns = now + self.period_ns
