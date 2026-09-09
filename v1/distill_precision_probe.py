"""Build and test isolated Distill precision candidates; never install a model."""
import argparse
import json
import os
from pathlib import Path
import statistics
import time

import cv2
import numpy as np

from compare_small_aspect import Engine, digest, preprocess
from compare_distill_small import oracle_error
from distill_small_experiment import ROOT, load_model


def ordered_nodes(graph):
    pending = list(graph.graph.node)
    known = {v.name for v in graph.graph.input} | {v.name for v in graph.graph.initializer}
    result = []
    while pending:
        ready = [node for node in pending if all(not name or name in known for name in node.input)]
        if not ready:
            raise ValueError('Unresolved or cyclic graph')
        for node in ready:
            result.append(node)
            known.update(node.output)
            pending.remove(node)
    del graph.graph.node[:]
    graph.graph.node.extend(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    import torch
    import onnx
    from onnxruntime.transformers.float16 import convert_float_to_float16
    from public_test_media import SOURCES
    torch.set_num_threads(1)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    source = ROOT/'out/p1-distill-small-20260909/distill-small-fp32.onnx'
    if digest(source) != '87b65b1130d240d1bb65557a0f321f088636bbaf3c4d20491b2fefb5476e344d':
        raise ValueError('Unexpected source export')
    report = dict(status='incomplete', source_sha256=digest(source), tf32=False,
                  contract=dict(atol=.001, rtol=.001), cases=[], builds={},
                  scope='Isolated precision/correctness check, not native live/VR performance.')
    model = None
    try:
        model, provenance = load_model()
        report['provenance'] = provenance
        with os.add_dll_directory('C:/TensorRT/TensorRT-11.2.1.2/bin'):
            import tensorrt as trt
            logger = trt.Logger(trt.Logger.WARNING)
            report['environment'] = dict(gpu=torch.cuda.get_device_name(), torch=torch.__version__,
                                          tensorrt=trt.__version__, cpu_threads=1)
            for precision in ('fp16', 'fp16-head'):
                graph = onnx.load(str(source))
                blocked = ([node.name for node in graph.graph.node if '/depth_head/' not in node.name]
                           if precision == 'fp16-head' else [])
                graph = convert_float_to_float16(graph, keep_io_types=True,
                    op_block_list=['Resize', 'LayerNormalization', 'Softmax'], node_block_list=blocked)
                ordered_nodes(graph)
                onnx.checker.check_model(graph)
                path = args.output/f'{precision}.onnx'
                onnx.save(graph, str(path))
                builder = trt.Builder(logger)
                network = builder.create_network(0)
                reader = trt.OnnxParser(network, logger)
                if not reader.parse_from_file(str(path)):
                    raise RuntimeError('Graph parse failed')
                config = builder.create_builder_config()
                config.clear_flag(trt.BuilderFlag.TF32)
                config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, 2*1024**3)
                started = time.perf_counter()
                print('BUILD', precision, flush=True)
                serialized = builder.build_serialized_network(network, config)
                if serialized is None:
                    raise RuntimeError('Precision build failed')
                plan = args.output/f'{precision}.plan'
                plan.write_bytes(bytes(serialized))
                report['builds'][precision] = dict(onnx_sha256=digest(path), plan_sha256=digest(plan),
                    seconds=time.perf_counter()-started, fp32_ops=['Resize', 'LayerNormalization', 'Softmax'])
                del serialized, config, reader, network, builder
                engine = Engine(plan, (518, 518), trt, torch, logger)
                try:
                    for name, expected in SOURCES.items():
                        media = ROOT/'out/public-video-source/uvg-vcm'/f'{name}.mp4'
                        if digest(media) != expected:
                            raise ValueError('Public source changed')
                        capture = cv2.VideoCapture(str(media))
                        try:
                            for index in range(6):
                                ok, bgr = capture.read()
                                if not ok or bgr.shape != (2160, 3840, 3):
                                    raise ValueError('Native 4K frame required')
                                tensor = preprocess(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), (518, 518))
                                with torch.inference_mode():
                                    reference = model(torch.from_numpy(tensor).cuda()).cpu().numpy()
                                for _ in range(5 if index == 0 else 0):
                                    engine.infer(tensor)
                                times = []
                                for _ in range(5):
                                    actual, elapsed = engine.infer(tensor)
                                    times.append(elapsed)
                                result = oracle_error(reference, actual)
                                result.update(precision=precision, source=name, frame=index,
                                              gpu_ms=times)
                                report['cases'].append(result)
                        finally:
                            capture.release()
                    rows = [row for row in report['cases'] if row['precision'] == precision]
                    report['builds'][precision].update(passed=all(row['passed'] for row in rows),
                        gpu_median_ms=statistics.median(t for row in rows for t in row['gpu_ms']))
                    print('RESULT', precision, report['builds'][precision], flush=True)
                finally:
                    engine.close()
                (args.output/'partial.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    finally:
        if model is not None:
            torch.cuda.synchronize()
            del model
    report['status'] = 'measured'
    report['script_sha256'] = digest(__file__)
    (args.output/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
