"""Run the existing real Qt/native benchmark with an explicit trial worker."""
import argparse
import os
from pathlib import Path
import sys

from base_trt_fp16_trial import manifest, trial_worker, write_manifest


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--candidate', choices=('fp32', 'mixed', 'selective'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args, remaining = parser.parse_known_args()
    manifest(args.candidate)
    os.environ['SCREENTO3D_FP16_TRIAL'] = args.candidate
    os.environ['SCREENTO3D_BASE_GRAPH'] = '0'
    os.environ['SCREENTO3D_BASE_INPUT'] = 'gpu'
    os.environ['SCREENTO3D_STEREO_RENDERER'] = 'cuda'
    from screento3d_app import live_sbs
    live_sbs.sbs_worker = trial_worker
    from benchmark_live_modes import main as benchmark
    sys.argv = [sys.argv[0], '--output', str(args.output), *remaining]
    try:
        benchmark()
    finally:
        if args.output.is_dir():
            write_manifest(args.output / 'precision-trial.json', args.candidate)


if __name__ == '__main__':
    main()
