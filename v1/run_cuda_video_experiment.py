"""Explicit diagnostic full pipeline; retains CPU product default."""
import argparse
import json
from pathlib import Path
import time
from unittest.mock import patch
import uuid
import numpy as np
from depthsbs_app import pipeline
from cuda_projection_experiment import CudaProjection


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--preview', action='store_true')
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    root = repo / 'out/cuda-video-experiment' / uuid.uuid4().hex
    root.mkdir(parents=True)
    bundle = repo / ('out/gpu-preview/DepthSBS-GPU-Preview/_internal' if args.preview else 'out/release/DepthSBS/_internal')
    with patch('depthsbs_app.resources.bundle_root', return_value=bundle):
        info = pipeline.probe_video(args.input)
        original = pipeline.project_eye
        results = {}
        for variant in ('cpu', 'cuda'):
            calls = 0
            elapsed = 0.
            with (root / f'{variant}.jsonl').open('w', encoding='utf-8') as log:
                def progress(event):
                    event['experimental_projection_override'] = variant
                    log.write(json.dumps(event) + '\n')
                    log.flush()
                class CheckedProjection(CudaProjection):
                    def __init__(self, width, height):
                        path = bundle / 'projection/projection.dll' if args.preview else None
                        super().__init__(width, height, dll_path=path)

                    def project(self, frame, depth, shift, conservative_coverage=False):
                        nonlocal calls, elapsed
                        start = time.perf_counter()
                        output = super().project(frame, depth, shift, conservative_coverage)
                        elapsed += time.perf_counter() - start
                        np.testing.assert_array_equal(output, original(frame, depth, shift, conservative_coverage))
                        calls += 1
                        return output
                print('START ' + variant, flush=True)
                result = pipeline.convert_video(args.input, root / f'{variant}.mp4', 'performance', progress,
                    projection_factory=CheckedProjection if variant == 'cuda' else None)
                results[variant] = dict(completion=result, exact_eye_checks=calls,
                    cuda_host_to_host_seconds=elapsed)
        report = dict(results=results,
            scope='Diagnostic CUDA conversion checks every eye against CPU. Total includes oracle overhead; not speed benchmark.',
            product_default_changed=False)
        (root / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(root / 'report.json')


if __name__ == '__main__':
    main()
