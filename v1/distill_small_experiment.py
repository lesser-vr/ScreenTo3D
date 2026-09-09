"""Pinned Distill Small oracle/export, isolated from application loaders."""
import argparse
import ast
import json
from pathlib import Path
import subprocess

from compare_small_aspect import digest

ROOT = Path(__file__).resolve().parents[1]
SOURCE_REVISION = '6d8f415392eafb49c96a38cc4dedbd09a1607f50'
WEIGHT_REVISION = '38095a41cca1e28a28e8bb6372c68df721455a2d'
WEIGHT_SHA256 = '56a173c0e1b5045bf6296a5c1fb16eace0bbde2eddc24b37532cb1774ac09caa'


def validate_source():
    source = ROOT / 'out/distill-source'
    if subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() != SOURCE_REVISION:
        raise ValueError('Unexpected Distill source revision')
    if subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True).strip():
        raise ValueError('Distill source is not clean')
    baseline = ROOT / 'out/da2-base-source/depth_anything_v2'
    candidate = source / 'distillanydepth/depth_anything_v2'
    checked = {}
    for path in baseline.rglob('*.py'):
        relative = path.relative_to(baseline)
        if str(relative) == 'dpt.py':
            continue
        if not (candidate / relative).is_file() or digest(path) != digest(candidate / relative):
            raise ValueError(f'Backbone/helper source differs: {relative}')
        checked[str(relative)] = digest(path)
    a = ast.parse((baseline / 'dpt.py').read_text())
    b = ast.parse((candidate / 'dpt.py').read_text())
    for name in ('_make_fusion_block', 'ConvBlock', 'DPTHead'):
        left = next(node for node in a.body if getattr(node, 'name', None) == name)
        right = next(node for node in b.body if getattr(node, 'name', None) == name)
        if ast.dump(left) != ast.dump(right):
            raise ValueError(f'Depth component differs: {name}')
    # At the pinned revision the remaining model forward difference is only an
    # unused shape unpack and returning (depth[B,1,H,W], features), rather than
    # depth[B,H,W]. Reuse the reviewed DA2 depth-only class, not hub/demo code.
    return checked


def load_model():
    import torch
    from safetensors.torch import load_file
    from da2_base_experiment import upstream_class
    checked = validate_source()
    weight = ROOT / 'out/models/distill-small/model.safetensors'
    if weight.stat().st_size != 99165428 or digest(weight) != WEIGHT_SHA256:
        raise ValueError('Distill Small integrity mismatch')
    cls = upstream_class()  # Also verifies the pinned clean DA2 source tree.
    model = cls(encoder='vits', features=64, out_channels=[48, 96, 192, 384])
    model.load_state_dict(load_file(str(weight), device='cpu'), strict=True)
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA required')
    model.to('cuda').eval()
    return model, dict(source_revision=SOURCE_REVISION, weight_revision=WEIGHT_REVISION,
                       weight_sha256=WEIGHT_SHA256, helper_hashes=checked,
                       parameter_count=sum(p.numel() for p in model.parameters()),
                       weight_license='Apache-2.0 model card', source_license='MIT',
                       adaptation='Reviewed DA2 depth-only forward; auxiliary features omitted')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    import torch
    import onnx
    torch.set_num_threads(1)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    model = None
    try:
        model, provenance = load_model()
        image = torch.zeros((1, 3, 518, 518), device='cuda', dtype=torch.float32)
        with torch.inference_mode():
            result = model(image)
            if tuple(result.shape) != (1, 518, 518) or not torch.isfinite(result).all():
                raise ValueError('Invalid oracle depth')
            torch.onnx.export(model, (image,), str(args.output / 'distill-small-fp32.onnx'),
                              opset_version=17, dynamo=False,
                              input_names=['pixel_values'], output_names=['predicted_depth'])
            onnx.checker.check_model(str(args.output / 'distill-small-fp32.onnx'))
            torch.cuda.synchronize()
        report = dict(provenance=provenance, shape=[1, 3, 518, 518],
                      onnx_sha256=digest(args.output / 'distill-small-fp32.onnx'),
                      torch=torch.__version__, onnx=onnx.__version__, tf32=False,
                      status='exported_not_numerically_validated')
        del image, result
    finally:
        if model is not None:
            torch.cuda.synchronize()
            del model
    (args.output / 'export.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
