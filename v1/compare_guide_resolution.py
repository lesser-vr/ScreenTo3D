"""Compare the full guide and a pinned 3:2 coefficient grid at native SBS size."""
import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
from unittest.mock import patch

import cv2

from check_da2_radius8 import BUILDS, Build, edge_frames, renderer
from compare_live_guide_radii import HFR, SOURCES, run_case
from depthsbs_app import motion_history
from depthsbs_app.desktop_jobs import BUNDLE, ROOT
from depthsbs_app.resources import configure_resource_root


CANDIDATE = Build('guide-two-thirds',
                  'a49e2e76d324f94dce88a8330e5d80fdfe4fe6f696214e99c35bfc563f526bce',
                  'ce64ac3a240b203910a95586ffe3e75551d449b11574d1db16f11b02b35dd167',
                  '8294e05bc6cf5db5f24be102f2f14d2959951ff59aa1ff9683c19b0636b1aa7c')


def make_renderer(build):
    def create(stack, mode, engine, w, h):
        return renderer(stack, build, mode, engine, w, h)
    return create


def native_worker(*args, **kwargs):
    """Select the candidate only in the owned capture benchmark's child process."""
    from depthsbs_app.live_sbs import sbs_worker
    from depthsbs_app.live_small_gpu_input import LiveSmallGpuInputTexture
    from depthsbs_app.live_source_gpu_texture import LiveSourceGpuTexture
    from depthsbs_app.live_texture_pool import LiveTexturePool

    directory = ROOT / 'out' / CANDIDATE.directory
    with ExitStack() as stack:
        for cls, file, digest in (
            (LiveSmallGpuInputTexture, 'small_input.dll', CANDIDATE.small),
            (LiveSourceGpuTexture, 'live_depth.dll', CANDIDATE.base),
        ):
            stack.enter_context(patch.multiple(cls, library_path=directory/file,
                                               library_sha256=digest, borrowed_layout_sha256=digest))
        stack.enter_context(patch.multiple(LiveTexturePool, library_path=directory/'live_texture_runtime.dll',
                                           library_sha256=CANDIDATE.pool))
        stack.enter_context(patch.object(motion_history, 'LAYOUTS',
                                         motion_history.LAYOUTS | {CANDIDATE.base, CANDIDATE.small}))
        return sbs_worker(*args, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--review', action='store_true', help='Write 3 s of matching Jockey Base Full SBS')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    configure_resource_root(BUNDLE)
    cv2.setNumThreads(2)
    runtime = Path('C:/TensorRT/TensorRT-11.2.1.2/bin')
    builds = {'full': make_renderer(BUILDS[1]), 'reduced': make_renderer(CANDIDATE)}
    layouts = motion_history.LAYOUTS | {CANDIDATE.base, CANDIDATE.small}
    with os.add_dll_directory(str(runtime)), patch.object(motion_history, 'LAYOUTS', layouts):
        cases = [('Jockey', 'balanced')] if args.review else [
            (clip, mode) for clip in (*HFR, *SOURCES, 'thin-flat') for mode in ('balanced', 'performance')]
        for clip, mode in cases:
            source = ((513, 289), edge_frames(513, 289)) if clip == 'thin-flat' else None
            count = 180 if args.review else 36
            case = run_case(clip, mode, count, args.output, runtime, args.review, builds=builds, source=source)
            assert case['summary']['frames'] == count
            print(json.dumps(case['summary'], allow_nan=False), flush=True)
            (args.output / f'{clip}-{mode}.json').write_text(json.dumps(case, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
