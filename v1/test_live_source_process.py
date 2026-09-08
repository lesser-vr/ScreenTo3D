"""Small real Qt source lifecycle and stalled-parent experiment (no GPU worker)."""

import argparse
import json
import time
from pathlib import Path

from live_benchmark_source import SourceProcess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a fresh report path")
    source = SourceProcess("FloorballGame")
    try:
        dpi = source.devicePixelRatioF()
        source.resize(round(1920 / dpi), round(1080 / dpi))
        time.sleep(1)
        before = source.refresh()
        # Deliberately do not pump a parent GUI or send control requests.
        time.sleep(3)
        after = source.refresh()
        elapsed = (after["observed_ns"] - before["observed_ns"]) / 1e9
        fps = (after["paint_count"] - before["paint_count"]) / elapsed
        assert after["sequence"] > before["sequence"] + 10
        assert after["paint_count"] > before["paint_count"] + 10
        assert len(after["stamps"]) <= 4096
        source.resize(640, 360)
        resized = source.refresh()
        assert (resized["width"], resized["height"]) == (640, 360)
        pid = source.pid
    finally:
        source.close()
    assert not source.process.is_alive()
    source.close()  # Idempotent cleanup.
    failed = SourceProcess("generated")
    failed.process.terminate()  # Inject failure in this owned child only.
    failed.process.join(5)
    caught = False
    try:
        failed.refresh()
    except RuntimeError:
        caught = True
    finally:
        failed.close()
    assert caught and not failed.process.is_alive()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = dict(
        passed=True,
        source_pid=pid,
        parent_stall_seconds=3,
        source_paint_fps=fps,
        before=before,
        after=after,
        normal_stop=True,
        resize_verified=True,
        injected_exit_detected=caught,
        scope="Source independence and bounded cleanup, not physical-display FPS",
    )
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps({k: v for k, v in report.items() if k not in ("before", "after")}))


if __name__ == "__main__":
    main()
