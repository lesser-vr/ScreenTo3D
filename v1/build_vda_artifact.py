"""Build, numerically validate and publish a local VDA fixed-profile artifact."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

from depthsbs_app.vda_artifacts import (SCHEMA, MODEL_ID, PROFILES, SOURCE_REVISION,
    WEIGHT_SHA256, sha256, load_manifest, validate_input)

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True, help='Validation video, at least 64 frames and compatible aspect ratio')
    parser.add_argument('--output', type=Path, required=True, help='New artifact directory; existing directories are never overwritten')
    parser.add_argument('--profile', choices=tuple(PROFILES), default='518x896')
    args = parser.parse_args()
    source = args.input.resolve(strict=True)
    shape = [1, 1, 3, *PROFILES[args.profile]]
    import cv2
    capture = cv2.VideoCapture(str(source))
    try:
        ok, frame = capture.read()
        if not ok:
            raise ValueError('Cannot decode validation input')
        validate_input(dict(width=frame.shape[1], height=frame.shape[0]), shape[-2:])
    finally:
        capture.release()
    output = args.output.resolve()
    if output.exists():
        parser.error('Output directory already exists; choose a new directory')
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = output.parent / (output.name + '.building-' + uuid.uuid4().hex)
    stage.mkdir()

    def run(label, script, *arguments):
        print('VDA build: ' + label, flush=True)
        log_path = stage / f'{label}.log'
        with log_path.open('w', encoding='utf-8') as log:
            result = subprocess.run([sys.executable, str(ROOT / 'v1' / script), *map(str, arguments)],
                cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=False)
        if result.returncode:
            raise RuntimeError(f'{label} failed; evidence retained at {log_path}')
        lines = log_path.read_text(encoding='utf-8').splitlines()
        candidate = Path(next(line for line in reversed(lines) if line.strip()))
        candidate = candidate.resolve(strict=True)
        if not candidate.is_relative_to(ROOT / 'out'):
            raise RuntimeError('Unexpected build output path')
        return candidate

    try:
        exported = run('export', 'export_vda_spike.py', '--input-size', '518', '--input-width', shape[-1]).parent
        rewritten = run('softmax', 'rewrite_vda_softmax.py', exported)
        folded = run('position', 'fold_vda_position.py', rewritten)
        report_path = run('parity', 'test_vda_trt.py', '--input', source, '--input-size', '518',
            '--frames', '64', '--onnx-dir', folded, '--input-width', shape[-1])
        report = json.loads(report_path.read_text(encoding='utf-8'))
        comparisons = report['comparisons']
        if (report.get('passed') is not True or len(comparisons) != 585 or
                report.get('input_shape') != shape or not all(c['passed'] for c in comparisons)):
            raise RuntimeError('Build did not meet VDA parity gate')
        engines = {}
        for name in ('warmup', 'cached'):
            plan = report_path.parent / f'{name}.plan'
            engines[name] = {'file': f'{name}.plan', 'sha256': sha256(plan)}
            shutil.copy2(plan, stage / f'{name}.plan')
        manifest = dict(schema=SCHEMA, model_id=MODEL_ID, input_shape=shape,
            source_revision=SOURCE_REVISION, weight_sha256=WEIGHT_SHA256,
            tensorrt=report['tensorrt'], torch=report['torch'], gpu=report['gpu'], compute_capability=[12, 0],
            precision='fp32', engines=engines, fixes=['stable-temporal-softmax', 'constant-position-resize'],
            validation=dict(passed=True, comparisons=585, atol=report['atol'], rtol=report['rtol'],
                input_sha256=sha256(source), max_abs=max(c['max_abs'] for c in comparisons)))
        (stage / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        shutil.copy2(report_path, stage / 'parity-report.json')
        shutil.copy2(folded / 'fold.json', stage / 'position-provenance.json')
        shutil.copy2(rewritten / 'rewrite.json', stage / 'softmax-provenance.json')
        shutil.copy2(ROOT / 'out/vda-source/LICENSE', stage / 'VDA-APACHE-2.0.txt')
        (stage / 'NOTICE.txt').write_text(
            'VDA Small local TensorRT artifact. Derived from DepthAnything/Video-Depth-Anything.\n'
            'Source and weights: Apache-2.0; see manifest for pinned provenance.\n'
            'Only load artifacts built locally or from a trusted producer. Hashes verify integrity, not authenticity.\n'
            'Not a portable engine: TensorRT version, GPU and fixed input profile must match.\n', encoding='utf-8')
        load_manifest(stage)
        if output.exists():
            raise RuntimeError('Output appeared during build; refusing overwrite')
        stage.rename(output)
        print(output / 'manifest.json', flush=True)
    except BaseException:
        print(f'Build incomplete; retained evidence: {stage}', file=sys.stderr, flush=True)
        raise


if __name__ == '__main__':
    main()
