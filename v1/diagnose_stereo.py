"""Matched-depth pre-encode ghosting experiment."""
import argparse
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
import cv2
import numpy as np
from screento3d_app.pipeline import preprocess
from screento3d_app.config import MODES
from screento3d_app.trt_backend import DepthEngine


class StereoSynthesizer:
    """Frozen pre-fix inverse/EMA baseline for reproducible ablation only."""
    def __init__(self, width, height, policy):
        self.width, self.height, self.policy = width, height, policy
        self.grid_x, self.grid_y = np.meshgrid(np.arange(width, dtype=np.float32), np.arange(height, dtype=np.float32))
        self.low = self.high = self.smoothed_depth = None

    def render(self, frame, depth):
        resized = cv2.resize(depth[0], (self.width, self.height), interpolation=cv2.INTER_CUBIC)
        low, high = np.percentile(resized, (2, 98))
        alpha = self.policy.temporal_alpha
        self.low = low if self.low is None else alpha * low + (1 - alpha) * self.low
        self.high = high if self.high is None else alpha * high + (1 - alpha) * self.high
        normalized = np.clip((resized - self.low) / max(self.high - self.low, 1e-6), 0, 1).astype(np.float32)
        self.smoothed_depth = normalized if self.smoothed_depth is None else alpha * normalized + (1 - alpha) * self.smoothed_depth
        disparity = (self.smoothed_depth - self.policy.convergence) * max(1, self.width * self.policy.divergence)
        left = cv2.remap(frame, self.grid_x + disparity * .5, self.grid_y, cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT101)
        right = cv2.remap(frame, self.grid_x - disparity * .5, self.grid_y, cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT101)
        return np.concatenate((left, right), axis=1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--frame', type=int, default=48)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = root / 'out/stereo-ghost-diagnosis'
    output.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(args.input)
    try:
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        ema = StereoSynthesizer(width, height, MODES['balanced'])
        current = StereoSynthesizer(width, height, replace(MODES['balanced'], temporal_alpha=1.0))
        with patch('screento3d_app.resources.bundle_root', return_value=root / 'out/release/ScreenTo3D/_internal'):
            with DepthEngine() as engine:
                for index in range(args.frame + 1):
                    ok, bgr = capture.read()
                    if not ok:
                        raise RuntimeError('Not enough input frames')
                    frame = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                    depth = engine.infer(preprocess(frame))
                    with_ema = ema.render(frame, depth)
                    without_ema = current.render(frame, depth)
                for name, pixels in [('source', frame), ('legacy-ema', with_ema), ('legacy-no-ema', without_ema)]:
                    cv2.imwrite(str(output / f'{name}.png'), cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR))
                np.savez(output / 'sample.npz', frame=frame, depth=depth,
                         normalized=current.smoothed_depth, ema=ema.smoothed_depth)
    finally:
        capture.release()
    print(output)


if __name__ == '__main__':
    main()
