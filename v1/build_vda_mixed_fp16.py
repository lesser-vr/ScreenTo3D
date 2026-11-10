"""Build the encoder-only mixed-FP16 streaming trial from pinned VDA ONNX graphs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper

from depthsbs_app.build_local_engine import compile_graph

SOURCE_PACK_SHA256 = '691bc8c7795004d9f5ee8229391af28781301c8cdd7a7dc38c508a7c7a2d5f44'


def lower_encoder(payload):
    model = onnx.load_from_string(payload)
    graph = model.graph
    weights = {t.name: t for t in graph.initializer}
    nodes = []
    converted = set()
    count = 0
    for node in graph.node:
        linear = (node.name.startswith('/blocks.') and node.op_type == 'MatMul'
                  and node.input[1] in weights)
        if not linear and node.name != '/patch_embed/proj/Conv':
            nodes.append(node)
            continue
        count += 1
        for i, original in enumerate(tuple(node.input)):
            name = node.name + '/input_fp16_' + str(i)
            if original in weights:
                name = original + '_mixed_fp16'
                if name not in converted:
                    data = numpy_helper.to_array(weights[original]).astype(np.float16)
                    graph.initializer.append(numpy_helper.from_array(data, name))
                    converted.add(name)
            else:
                nodes.append(helper.make_node('Cast', [original], [name], to=TensorProto.FLOAT16))
            node.input[i] = name
        output = node.output[0]
        node.output[0] = output + '_mixed_fp16'
        nodes.extend([node, helper.make_node('Cast', [node.output[0]], [output], to=TensorProto.FLOAT)])
    if count != 49:
        raise ValueError(f'Expected patch embedding and four projections per encoder block, got {count}')
    used = {key for n in nodes for key in n.input} | {x.name for x in graph.output}
    initializers = [t for t in graph.initializer if t.name in used]
    del graph.initializer[:]
    graph.initializer.extend(initializers)
    del graph.node[:]
    graph.node.extend(nodes)
    onnx.checker.check_model(model)
    return model.SerializeToString()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pack', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--runtime', type=Path, required=True)
    args = parser.parse_args()
    from depthsbs_app.engine_cache import TRT_VERSION
    with args.pack.open('rb') as src:
        if hashlib.file_digest(src, 'sha256').hexdigest() != SOURCE_PACK_SHA256:
            raise ValueError('Expected the original verified VDA FP32 ONNX pack')
    args.destination.mkdir(parents=True, exist_ok=False)
    with os.add_dll_directory(str(args.runtime.resolve())), ZipFile(args.pack) as archive:
        import tensorrt as trt
        if trt.__version__ != TRT_VERSION:
            raise ValueError('Unexpected TensorRT version')
        logger = trt.Logger(trt.Logger.WARNING)
        for width in (924, 896):
            profile = args.destination / f'518x{width}-fp16'
            profile.mkdir()
            records = {}
            for stage in ('warmup', 'cached'):
                payload = archive.read(f'518x{width}-fp32/{stage}.onnx')
                graph = lower_encoder(payload)
                print(f'Building {width} {stage}', flush=True)
                (profile / f'{stage}.onnx').write_bytes(graph)
                records[stage] = compile_graph(graph, profile / f'{stage}.plan', trt, logger)
                records[stage]['graph_sha256'] = hashlib.sha256(graph).hexdigest()
            (profile/'trial.json').write_text(json.dumps(records, indent=2))


if __name__ == '__main__':
    main()
