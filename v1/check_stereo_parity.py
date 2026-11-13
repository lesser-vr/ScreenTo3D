"""Nearest-path CPU optimization parity only; excludes the new coverage policy."""
import subprocess
import types
import numpy as np
from screento3d_app import stereo


def main():
    baseline = types.ModuleType('baseline')
    exec(subprocess.check_output([
        'git', 'show', '55112b6:v1/screento3d_app/stereo.py'
    ], text=True), baseline.__dict__)
    rng = np.random.default_rng(2048)
    for height, width in ((1, 1), (4, 16), (32, 64), (100, 100)):
        for _ in range(20):
            frame = rng.integers(0, 256, (height, width, 3), dtype=np.uint8)
            depth = rng.random((height, width), dtype=np.float32)
            shift = rng.uniform(-width * 2, width * 2, depth.shape).astype(np.float32)
            np.testing.assert_array_equal(stereo.project_eye(frame, depth, shift),
                                          baseline.project_eye(frame, depth, shift))
            frame[:] = rng.integers(0, 256, 3, dtype=np.uint8)
            frame[height//4:height*3//4, width//4:width*3//4] = 127
            np.testing.assert_array_equal(stereo.refine_flat_background(frame, depth),
                                          baseline.refine_flat_background(frame, depth))
    sample = np.load('out/stereo-ghost-diagnosis/sample.npz')
    for name in ('normalized', 'ema'):
        frame = sample['frame']
        guided = stereo.guide_depth(frame, sample[name])
        refined = stereo.refine_flat_background(frame, guided)
        np.testing.assert_array_equal(refined, baseline.refine_flat_background(frame, guided))
        for sign in (-1, 1):
            shift = sign * (refined - .45) * frame.shape[1] * .026 * .5
            np.testing.assert_array_equal(stereo.project_eye(frame, refined, shift),
                                          baseline.project_eye(frame, refined, shift))
    print('PASS: 80 randomized cases and real sample, both eyes and depth variants; exact equality')


if __name__ == '__main__':
    main()
