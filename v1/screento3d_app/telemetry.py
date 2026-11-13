"""Bounded wall-clock stage statistics."""
from collections import deque
from contextlib import contextmanager
import math
import time


class StageMetrics:
    def __init__(self, capacity=2048):
        if capacity < 1:
            raise ValueError('capacity must be positive')
        self.capacity = capacity
        self.stages = {}

    def observe(self, name, seconds):
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError('invalid duration')
        stage = self.stages.setdefault(name, [0, 0.0, 0.0, deque(maxlen=self.capacity)])
        milliseconds = seconds * 1000
        stage[0] += 1
        stage[1] += milliseconds
        stage[2] = max(stage[2], milliseconds)
        stage[3].append(milliseconds)

    @contextmanager
    def measure(self, name):
        started = time.perf_counter()
        try:
            yield
        finally:
            self.observe(name, time.perf_counter() - started)

    def summary(self):
        result = {}
        for name, (count, total, maximum, window) in self.stages.items():
            samples = sorted(window)

            def percentile(q):
                position = (len(samples) - 1) * q
                lower = int(position)
                upper = min(lower + 1, len(samples) - 1)
                return samples[lower] + (samples[upper] - samples[lower]) * (position - lower)

            result[name] = dict(count=count, sample_count=len(samples),
                                mean_ms=total / count, max_ms=maximum,
                                p50_ms=percentile(.50), p95_ms=percentile(.95),
                                p99_ms=percentile(.99))
        return result
