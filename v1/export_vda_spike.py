"""Fixed-shape structural ONNX experiment, not a production engine builder."""
import json
import argparse
import uuid
import traceback
from collections import Counter

import onnx
import torch

from vda_streaming_experiment import ROOT, VdaStreamingEngine


class Step(torch.nn.Module):
    def __init__(self, model):
        super().__init__()
        self.model = model

    def forward(self, image, *cache):
        depth, updated = self.model.forward_depth(self.model.forward_features(image),
            image.shape, cached_hidden_state_list=list(cache) if cache else None)
        return (depth, *updated)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plain-attention', action='store_true')
    parser.add_argument('--input-size', type=int, choices=(140, 518), default=140)
    parser.add_argument('--input-width', type=int, choices=(896, 924), default=896)
    args = parser.parse_args()
    root = ROOT / 'out/vda-onnx-spike' / uuid.uuid4().hex
    root.mkdir(parents=True)
    shape = (1, 1, 3, args.input_size, 252 if args.input_size == 140 else args.input_width)
    report = dict(passed=False, scope='FP32 fixed shape structural export only', input_shape=shape,
                  torch=torch.__version__, onnx=onnx.__version__, graphs=[])
    try:
        with VdaStreamingEngine(input_size=args.input_size) as engine, torch.no_grad():
            if args.plain_attention:
                from vda_plain_attention import install
                report['plain_attention_modules'] = install(engine.model)
            step = Step(engine.model).eval()
            image = torch.zeros(shape, device='cuda')
            warmup = step(image)
            caches = tuple(value.repeat(1, 31, 1) for value in warmup[1:])
            for label, inputs in [('warmup', (image,)), ('cached', (image, *caches))]:
                path = root / f'{label}.onnx'
                torch.onnx.export(step, inputs, str(path), opset_version=17,
                    dynamo=False, input_names=['image'] + [f'cache_{i}' for i in range(len(inputs)-1)],
                    output_names=['depth'] + [f'new_cache_{i}' for i in range(8)])
                graph = onnx.load(str(path))
                onnx.checker.check_model(graph)
                report['graphs'].append(dict(name=label, bytes=path.stat().st_size,
                    operators=dict(Counter(node.op_type for node in graph.graph.node)),
                    inputs=[item.name for item in graph.graph.input],
                    outputs=[item.name for item in graph.graph.output]))
                print('PASS: ' + label, flush=True)
        report['passed'] = True
    except Exception:
        report['error'] = traceback.format_exc()
        raise
    finally:
        (root / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(root / 'report.json', flush=True)


if __name__ == '__main__':
    main()
