"""Compare bounded backdrop-boundary guards on the saved matched-depth sample."""
from pathlib import Path
import inspect
import types
import cv2
import numpy as np
from depthsbs_app import stereo

root = Path('out/stereo-ghost-diagnosis')
sample = np.load(root / 'sample.npz')
frame = sample['frame']
source = inspect.getsource(stereo.refine_flat_background)
for name in ('normalized', 'ema'):
    depth = stereo.refine_flat_background(frame, stereo.guide_depth(frame, sample[name]))
    shift = -(depth - .45) * frame.shape[1] * .026 * .5
    output = stereo.project_eye(frame, depth, shift, conservative_coverage=True)
    cv2.imwrite(str(root / f'hand-coverage-{name}.jpg'), cv2.cvtColor(
        cv2.resize(output[320:495, 310:425], None, fx=3, fy=3, interpolation=cv2.INTER_NEAREST), cv2.COLOR_RGB2BGR))
    cv2.imwrite(str(root / f'hand-coverage-full-{name}.jpg'), cv2.cvtColor(output[70:530, 280:760], cv2.COLOR_RGB2BGR))
for guard in (0, 1, 2, 3):
    candidate = types.ModuleType('candidate')
    candidate.np, candidate.cv2 = np, cv2
    candidate.uniform_color_mask = stereo.uniform_color_mask
    modified = source.replace('    foreground = (~background).astype(np.uint8)',
        f'    background = cv2.erode(background.astype(np.uint8), np.ones(({guard*2+1}, {guard*2+1}), np.uint8)) != 0\n'
        '    foreground = (~background).astype(np.uint8)')
    exec(modified, candidate.__dict__)
    for name in ('normalized', 'ema'):
        depth = candidate.refine_flat_background(frame, stereo.guide_depth(frame, sample[name]))
        shift = -(depth - .45) * frame.shape[1] * .026 * .5
        output = stereo.project_eye(frame, depth, shift)
        crop = output[320:495, 310:425]
        cv2.imwrite(str(root / f'hand-guard-{guard}-{name}.jpg'),
                    cv2.cvtColor(cv2.resize(crop, None, fx=3, fy=3, interpolation=cv2.INTER_NEAREST), cv2.COLOR_RGB2BGR))
