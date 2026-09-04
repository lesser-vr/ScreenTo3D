"""Non-overlapping wall-clock checkpoints for completed conversions."""
import time


class Lifecycle:
    def __init__(self, clock=time.perf_counter):
        self.clock = clock
        self.last = clock()
        self.seconds = {}

    def checkpoint(self, name):
        if name in self.seconds:
            raise ValueError('duplicate lifecycle checkpoint')
        now = self.clock()
        self.seconds[name] = now - self.last
        self.last = now
