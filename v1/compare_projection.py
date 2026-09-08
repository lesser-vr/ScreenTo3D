from pathlib import Path
import time
import cv2
import numpy as np
from depthsbs_app.stereo import project_eye, guide_depth, refine_flat_background

root = Path(__file__).resolve().parents[1] / 'out/stereo-ghost-diagnosis'
sample = np.load(root / 'sample.npz')
frame = sample['frame']
for name in ('normalized', 'ema'):
    depth = refine_flat_background(frame, guide_depth(frame, sample[name]))
    disparity = (depth - .45) * frame.shape[1] * .026
    started = time.perf_counter()
    # Preserve historical eye order: left projects negative, right positive.
    output = np.concatenate((project_eye(frame, depth, -.5 * disparity, conservative_coverage=True),
                             project_eye(frame, depth, .5 * disparity, conservative_coverage=True)), axis=1)
    print(name, time.perf_counter() - started)
    cv2.imwrite(str(root / f'flat-backdrop-{name}.png'), cv2.cvtColor(output, cv2.COLOR_RGB2BGR))
    cv2.imwrite(str(root / f'flat-backdrop-{name}-crop.jpg'), cv2.cvtColor(output[70:530, 280:760], cv2.COLOR_RGB2BGR))
