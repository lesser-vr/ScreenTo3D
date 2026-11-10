"""Bounded 2x experimental presentation timeline, independent of Qt/CUDA."""
from dataclasses import dataclass


@dataclass
class Timeline:
    previous_source: int | None = None
    last_due: int = 0

    def plan(self, source: int, ready: int, reset: bool):
        if source <= 0 or ready <= 0 or source - ready > 100_000_000:
            raise ValueError("Invalid source/ready clock")
        interval = source - self.previous_source if self.previous_source is not None else 0
        interpolate = not reset and 0 < interval <= 100_000_000
        # Preserve actual ready/source times when fast WGC processing finishes
        # before the compositor stamp; schedule after both without clock clamping.
        first = max(ready, source, self.last_due + 1)
        if first - ready > 100_000_000:
            raise RuntimeError("VFG presentation backlog exceeded bound")
        if interpolate:
            result = ((1, first, self.previous_source + interval // 2, self.previous_source),
                      (0, first + interval // 2, source, source))
        else:
            result = ((0, first, source, source),)
        self.previous_source, self.last_due = source, result[-1][1]
        return result
