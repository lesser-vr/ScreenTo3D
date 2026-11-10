"""Build isolated spatial-attention profiles from the verified VDA Small v2 pack."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from zipfile import ZipFile

import onnx
from onnx import TensorProto, helper

from depthsbs_app.engine_cache import TRT_VERSION

V2_SHA = 'd99ad9d3a3e40454b1726ccd304701dd9815ce3e846a9cdd400f25cf8d979f0d'


def spatial_graph(payload, *, wide_scores=False, keep_fp32=()):
    """Round the spatial QK and AV operands except in the specified v2 blocks."""
    model = onnx.load_from_string(payload)
    graph = model.graph
    if set(keep_fp32) - set(range(12)):
        raise ValueError('Spatial block indices must be in 0..11')
    blocks = set(range(12)).difference(keep_fp32)
    targets = {f'/blocks.{block}/attn/{op}' for block in blocks for op in ('MatMul', 'MatMul_1')}
    softmaxes = {f'/blocks.{block}/attn/Softmax' for block in blocks} if wide_scores else set()
    nodes = []
    for node in graph.node:
        if node.name in softmaxes:
            softmaxes.remove(node.name)
            axis = next((a.i for a in node.attribute if a.name == 'axis'), -1)
            if node.op_type != 'Softmax' or axis != -1:
                raise ValueError(f'Unexpected spatial Softmax at {node.name}')
            prefix = node.name + '/wide'
            # Keep the max-shifted score reduction visible in the engine inspector.
            axes = prefix + '/axes'
            graph.initializer.append(helper.make_tensor(axes, TensorProto.INT64, [1], [-1]))
            maximum, shift, exponential, total = [prefix + '/' + s for s in ('max', 'shift', 'exp', 'sum')]
            nodes.extend((
                helper.make_node('ReduceMax', list(node.input), [maximum], name=maximum, axes=[-1], keepdims=1),
                helper.make_node('Sub', [node.input[0], maximum], [shift], name=shift),
                helper.make_node('Exp', [shift], [exponential], name=exponential),
                helper.make_node('ReduceSum', [exponential, axes], [total], name=total, keepdims=1),
                helper.make_node('Div', [exponential, total], list(node.output), name=prefix + '/divide'),
            ))
            continue
        if node.name not in targets:
            nodes.append(node)
            continue
        if node.op_type != 'MatMul' or len(node.input) != 2 or len(node.output) != 1:
            raise ValueError(f'Unexpected attention graph at {node.name}')
        targets.remove(node.name)
        # Express rounded inputs and FP32 MatMul semantics in ONNX. TensorRT
        # can fuse this pattern, so its physical tactics are measured separately.
        for i, source in enumerate(tuple(node.input)):
            half = f'{node.name}/operand_{i}_fp16'
            accum = f'{node.name}/operand_{i}_accum'
            nodes.append(helper.make_node('Cast', [source], [half], to=TensorProto.FLOAT16))
            nodes.append(helper.make_node('Cast', [half], [accum], to=TensorProto.FLOAT))
            node.input[i] = accum
        output = node.output[0]
        if wide_scores and node.name.endswith('/attn/MatMul'):
            nodes.append(node)
            continue
        wide = output + '_accum'
        half = output + '_fp16'
        node.output[0] = wide
        nodes.extend((node, helper.make_node('Cast', [wide], [half], to=TensorProto.FLOAT16),
                      helper.make_node('Cast', [half], [output], to=TensorProto.FLOAT)))
    if targets or softmaxes:
        raise ValueError(f'Missing attention nodes: {sorted(targets | softmaxes)}')
    del graph.node[:]
    graph.node.extend(nodes)
    onnx.checker.check_model(model)
    return model.SerializeToString()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pack', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--runtime', required=True, type=Path)
    parser.add_argument('--wide-scores', action='store_true',
                        help='Retain FP32 scores into an explicit max-shifted FP32 Softmax')
    parser.add_argument('--keep-fp32', type=int, choices=range(12), action='append', default=[],
                        help='Keep spatial attention in this zero-based block at v2 precision; repeatable')
    args = parser.parse_args()
    with args.pack.open('rb') as src, os.add_dll_directory(str(args.runtime.resolve())):
        if hashlib.file_digest(src, 'sha256').hexdigest() != V2_SHA:
            raise ValueError('Expected the pinned VDA v2 ONNX pack')
        import tensorrt as trt
        if trt.__version__ != TRT_VERSION:
            raise ValueError('Unexpected TensorRT runtime')
        args.output.mkdir(parents=True, exist_ok=False)
        logger = trt.Logger(trt.Logger.WARNING)
        with ZipFile(src) as archive:
            for width in (924, 896):
                folder = args.output / f'518x{width}-fp16'
                folder.mkdir()
                records = {}
                for stage in ('warmup', 'cached'):
                    graph = spatial_graph(archive.read(f'{folder.name}/{stage}.onnx'),
                                          wide_scores=args.wide_scores, keep_fp32=args.keep_fp32)
                    builder = trt.Builder(logger)
                    network = builder.create_network(0)
                    reader = trt.OnnxParser(network, logger)
                    if not reader.parse(graph):
                        raise ValueError([str(reader.get_error(i)) for i in range(reader.num_errors)])
                    config = builder.create_builder_config()
                    config.clear_flag(trt.BuilderFlag.TF32)
                    config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, 2 * 1024**3)
                    config.profiling_verbosity = trt.ProfilingVerbosity.DETAILED
                    print('Building', width, stage, flush=True)
                    serialized = builder.build_serialized_network(network, config)
                    if serialized is None:
                        raise RuntimeError('Failed to build trial engine')
                    data = bytes(serialized)
                    (folder / f'{stage}.plan').write_bytes(data)
                    (folder / f'{stage}.onnx').write_bytes(graph)
                    records[stage] = {
                        'file': f'{stage}.plan',
                        'bytes': len(data),
                        'sha256': hashlib.sha256(data).hexdigest(),
                        'graph_sha256': hashlib.sha256(graph).hexdigest(),
                    }
                (folder / 'trial.json').write_text(json.dumps(records, indent=2))


if __name__ == '__main__':
    main()
