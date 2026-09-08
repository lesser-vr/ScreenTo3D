"""Matched-input spatial timings; not end-to-end throughput."""
import json
import time
import numpy as np
from depthsbs_app.stereo import guide_depth, refine_flat_background, project_eye


def main():
    sample = np.load('out/stereo-ghost-diagnosis/sample.npz')
    frame, depth = sample['frame'], sample['normalized']
    timings = {}
    def measure(name, fn):
        fn()
        samples = []
        for _ in range(12):
            start = time.perf_counter()
            result = fn()
            samples.append((time.perf_counter() - start) * 1000)
        timings[name] = float(np.median(samples))
        return result
    guided = measure('guide_ms', lambda: guide_depth(frame, depth))
    refined = measure('background_ms', lambda: refine_flat_background(frame, guided))
    shift = (refined - .45) * frame.shape[1] * .026 * .5
    measure('nearest_one_eye_ms', lambda: project_eye(frame, refined, shift))
    measure('coverage_one_eye_ms', lambda: project_eye(frame, refined, shift, conservative_coverage=True))
    print(json.dumps(timings, indent=2))


if __name__ == '__main__':
    main()
