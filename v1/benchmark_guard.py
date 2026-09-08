"""Explicit diagnostic stop guard; never changes product pacing."""


class OutputRateGuard:
    def __init__(self, threshold, now, count, window=3.0):
        if threshold <= 0 or window <= 0:
            raise ValueError("Positive guard threshold/window required")
        self.threshold, self.window = threshold, window
        self.start, self.count = now, count

    def due(self, now):
        return now - self.start >= self.window

    def observe(self, now, count):
        if not self.due(now):
            return None
        elapsed = now - self.start
        rate = (count - self.count) / elapsed
        self.start, self.count = now, count
        if rate < self.threshold:
            return dict(output_fps=rate, seconds=elapsed, threshold_fps=self.threshold)
        return None
