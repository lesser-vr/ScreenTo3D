"""CPU-only safety/layout helpers for bounded VDA comparison diagnostics."""
import cv2
import numpy as np


def validate_metadata(metadata, limit):
    if type(limit) is not int or not 1 <= limit <= 124:
        raise ValueError('Comparison frame limit must be 1..124')
    if not all(16 <= metadata[key] <= 1920 for key in ('width', 'height')):
        raise ValueError('Source reference comparison supports dimensions 16..1920; not 4K')
    count = metadata['total_frames']
    if count < 0 or count > limit:
        raise ValueError('Comparison exceeds the declared frame budget')


class BoundedEngine:
    """Limit actual inference, even when container frame counts are inaccurate."""
    def __init__(self, engine, limit):
        if type(limit) is not int or not 1 <= limit <= 124:
            raise ValueError('Comparison frame limit must be 1..124')
        self.engine, self.limit, self.calls = engine, limit, 0

    def infer(self, frame):
        if self.calls >= self.limit:
            raise ValueError('Actual decoded frames exceed comparison budget; input is not truncated silently')
        result = self.engine.infer(frame)
        self.calls += 1
        return result

    def reset(self, reason):
        self.engine.reset(reason)

    def telemetry(self):
        return {**self.engine.telemetry(), 'comparison_actual_frames': self.calls, 'comparison_frame_limit': self.limit}

    def close(self):
        self.engine.close()

    def __enter__(self):
        self.engine.__enter__()
        return self

    def __exit__(self, *exc):
        return self.engine.__exit__(*exc)


def validate_runs(runs, declared_frames, compared_frames):
    counts = [run['frames'] for run in runs.values()]
    if not counts or counts[0] <= 0 or any(count != compared_frames for count in counts):
        raise ValueError('Reference comparison frame counts disagree or are empty')
    if declared_frames and compared_frames != declared_frames:
        raise ValueError('Decoded frame count does not match input metadata')
    hashes = [run['telemetry']['diagnostic_hashes']['decoded_rgb'] for run in runs.values()]
    if len(set(hashes)) != 1:
        raise ValueError('Source pixels changed between comparison runs')


def lower_region(width, height):
    """Normalized original avatar inspection region; generic lower-frame ROI."""
    if min(width, height) < 16:
        raise ValueError('Inspection image is too small')
    return (int(width * 200 / 1056), int(height * 280 / 608),
            min(width, int(width * 850 / 1056)), min(height, int(height * 600 / 608)))


def inspection_sheet(rows, width, height, *, lower=False):
    output = []
    x0, y0, x1, y1 = lower_region(width, height)
    for label, frame in rows:
        if frame.dtype != np.uint8 or frame.shape != (height, width*2, 3):
            raise ValueError('Inspection rows must be matching uint8 SBS frames')
        view = (np.concatenate([frame[y0:y1, x0:x1], frame[y0:y1, width+x0:width+x1]], axis=1)
                if lower else frame)
        # Bound artifact size without changing aspect ratio; retain labels outside pixels.
        scale = min(1.0, 1600 / view.shape[1])
        view = cv2.resize(view, (max(1, round(view.shape[1]*scale)), max(1, round(view.shape[0]*scale))),
                          interpolation=cv2.INTER_AREA)
        header = np.full((38, view.shape[1], 3), 245, np.uint8)
        cv2.putText(header, label, (8, 26), cv2.FONT_HERSHEY_SIMPLEX, .65, (20, 20, 20), 1)
        output.append(np.concatenate([header, view], axis=0))
    if not output:
        raise ValueError('Inspection requires at least one row')
    return np.concatenate(output, axis=0)
