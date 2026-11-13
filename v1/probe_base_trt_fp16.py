"""Build isolated, explicitly typed FP16 Base engines and measure public inputs.

Does not install plans or change application artifact trust/defaults.
"""
import argparse
from collections import Counter
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import statistics
import time
import traceback

import cv2
import numpy as np
import torch

from da2_base_experiment import Da2BaseOracle
from screento3d_app.da2_base import binding, preprocess
from screento3d_app.desktop_jobs import ROOT
from public_test_media import PublicFrames
from base_trt_fp16_trial import installed


SOURCE = ROOT / 'out/da2-base-trt/c08f132882cc47bfaca7d581a7da5ed7/model.onnx'
SOURCE_HASH = '3c7912b2934004626e1e5cbfb6b3ee0446909bd20a411cf8709e324220f945b2'
SHAPE = (518, 924)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(root, recipe, trt, *, source=SOURCE, source_hash=SOURCE_HASH):
    import onnx
    from onnxruntime.transformers.float16 import convert_float_to_float16

    if digest(source) != source_hash:
        raise ValueError('Source ONNX checksum mismatch')
    graph = onnx.load(str(source))
    blocked = []
    if recipe == 'selective':
        # Lower only MLP/patch/head convolutions; keep residuals, attention and
        # final output-conv2 FP32. This is a new recipe, not the old head-only one.
        blocked = [node.name for node in graph.graph.node
                   if node.op_type not in ('MatMul', 'Conv', 'ConvTranspose')
                   or '/attn/' in node.name or '/output_conv2/' in node.name]
    graph = convert_float_to_float16(
        graph, keep_io_types=True,
        op_block_list=['Resize', 'LayerNormalization', 'Softmax'],
        node_block_list=blocked)
    available = {item.name for item in graph.graph.input}
    available.update(item.name for item in graph.graph.initializer)
    pending, ordered = list(graph.graph.node), []
    while pending:
        ready = [node for node in pending if all(not x or x in available for x in node.input)]
        if not ready:
            raise ValueError('Converted graph cannot be topologically sorted')
        for node in ready:
            ordered.append(node)
            available.update(node.output)
            pending.remove(node)
    del graph.graph.node[:]
    graph.graph.node.extend(ordered)
    onnx.checker.check_model(graph)
    onnx_path, plan_path = root / f'{recipe}.onnx', root / f'{recipe}.plan'
    onnx.save(graph, str(onnx_path))
    counts = Counter(onnx.TensorProto.DataType.Name(x.data_type) for x in graph.graph.initializer)
    logger = trt.Logger(trt.Logger.WARNING)
    builder = trt.Builder(logger)
    network = builder.create_network(0)
    parser = trt.OnnxParser(network, logger)
    if not parser.parse_from_file(str(onnx_path)):
        raise RuntimeError('\n'.join(str(parser.get_error(i)) for i in range(parser.num_errors)))
    config = builder.create_builder_config()
    config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, 2 * 1024**3)
    config.clear_flag(trt.BuilderFlag.TF32)
    config.profiling_verbosity = trt.ProfilingVerbosity.DETAILED
    start = time.perf_counter()
    payload = builder.build_serialized_network(network, config)
    if payload is None:
        raise RuntimeError(f'{recipe} build failed')
    plan_path.write_bytes(bytes(payload))
    return dict(recipe=recipe, onnx_sha256=digest(onnx_path),
                plan_sha256=digest(plan_path), plan_bytes=plan_path.stat().st_size,
                initializer_types=dict(counts), blocked_nodes=blocked,
                build_seconds=time.perf_counter() - start)


class Candidate:
    def __init__(self, root, metadata, trt, stream):
        path = root / f"{metadata['recipe']}.plan"
        if digest(path) != metadata['plan_sha256']:
            raise ValueError('Newly built test plan changed')
        self.stream = stream
        self.logger = trt.Logger(trt.Logger.WARNING)
        self.runtime = trt.Runtime(self.logger)
        self.engine = self.runtime.deserialize_cuda_engine(path.read_bytes())
        if self.engine is None:
            raise RuntimeError('Candidate deserialization failed')
        expected = {'image': ((1, 3, *SHAPE), trt.TensorIOMode.INPUT),
                    'depth': ((1, *SHAPE), trt.TensorIOMode.OUTPUT)}
        if self.engine.num_io_tensors != 2:
            raise ValueError('Unexpected candidate I/O')
        for i in range(2):
            name = self.engine.get_tensor_name(i)
            if (name not in expected or self.engine.get_tensor_dtype(name) != trt.float32
                    or (tuple(self.engine.get_tensor_shape(name)), self.engine.get_tensor_mode(name)) != expected[name]):
                raise ValueError('Candidate FP32 I/O contract changed')
        inspector = self.engine.create_engine_inspector()
        (root / f"{metadata['recipe']}-layers.json").write_text(
            inspector.get_engine_information(trt.LayerInformationFormat.JSON), encoding='utf-8')
        self.context = self.engine.create_execution_context()
        if self.context is None:
            raise RuntimeError('Candidate context creation failed')
        self.output = torch.empty((1, *SHAPE), device='cuda', dtype=torch.float32)

    def run(self, tensor):
        if not (self.context.set_tensor_address('image', tensor.data_ptr())
                and self.context.set_tensor_address('depth', self.output.data_ptr())):
            raise RuntimeError('Candidate tensor binding failed')
        if not self.context.execute_async_v3(self.stream.cuda_stream):
            raise RuntimeError('Candidate execution failed')
        return self.output

    def close(self):
        self.stream.synchronize()
        self.context = self.engine = self.runtime = self.output = None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(4)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    report = dict(completed=False, source_onnx_sha256=SOURCE_HASH,
                  torch=torch.__version__, gpu=torch.cuda.get_device_name(), shape=[1, 3, *SHAPE],
                  scope='isolated TensorRT model GPU timing and depth differences; no app FPS, SBS, perceptual or binocular acceptance',
                  raw_gate=dict(atol=.001, rtol=.001), builds=[], cases=[])
    def save():
        (args.output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    try:
        with ExitStack() as stack, torch.inference_mode():
            runtime = Path('C:/TensorRT/TensorRT-11.2.1.2/bin')
            stack.enter_context(os.add_dll_directory(str(runtime)))
            import tensorrt as trt
            if trt.__version__ != '11.2.1.2':
                raise RuntimeError('Unexpected TensorRT version')
            report['tensorrt'] = trt.__version__
            for recipe in ('mixed', 'selective'):
                print(f'Building {recipe}', flush=True)
                report['builds'].append(build(args.output, recipe, trt))
                save()
                print(f'Built {recipe}', flush=True)
            with installed('fp32'):
                backend = binding(ROOT / 'out/da2-base-local', runtime)
                backend.input_validator(dict(width=1920, height=1080))
                control = stack.enter_context(backend.engine_factory(None))
            report['control_plan_sha256'] = control.telemetry()['plan_sha256']
            oracle = stack.enter_context(Da2BaseOracle())
            candidates = {}
            for metadata in report['builds']:
                candidate = Candidate(args.output, metadata, trt, control.stream)
                stack.callback(candidate.close)
                candidates[metadata['recipe']] = candidate
            with torch.cuda.stream(control.stream):
                tensor = torch.empty((1, 3, *SHAPE), device='cuda')
                if not (control.context.set_tensor_address('image', tensor.data_ptr())
                        and control.context.set_tensor_address('depth', control.output.data_ptr())):
                    raise RuntimeError('Control binding failed')
                def fp32():
                    if not control.context.execute_async_v3(control.stream.cuda_stream):
                        raise RuntimeError('Control execution failed')
                    return control.output
                methods = {'fp32': fp32, **{name: lambda c=c: c.run(tensor) for name, c in candidates.items()}}
                first = next(iter(PublicFrames('FloorballGame', 1)))
                tensor.copy_(torch.from_numpy(preprocess(first, SHAPE))[None].to('cuda'))
                for _ in range(10):
                    for method in methods.values():
                        method()
                control.stream.synchronize()
                timings = {name: [] for name in methods}
                for repeat in range(60):
                    names = list(methods)
                    offset = repeat % len(names)
                    for name in names[offset:] + names[:offset]:
                        a, b = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
                        a.record(control.stream)
                        methods[name]()
                        b.record(control.stream)
                        b.synchronize()
                        timings[name].append(a.elapsed_time(b))
                report['timing_samples_ms'] = timings
                report['median_model_gpu_ms'] = {name: statistics.median(t) for name, t in timings.items()}
                print(report['median_model_gpu_ms'], flush=True)
                save()
                def compare(rgb, label):
                    tensor.copy_(torch.from_numpy(preprocess(rgb, SHAPE))[None].to('cuda'))
                    reference = oracle.model(tensor).float()
                    control_value = fp32()
                    low, high = torch.quantile(reference.flatten(), torch.tensor([.02, .98], device='cuda'))
                    scale = (high - low).clamp_min(1e-6)
                    for name, method in methods.items():
                        value = control_value if name == 'fp32' else method()
                        finite = bool(torch.isfinite(value).all() and torch.isfinite(reference).all())
                        row = dict(case=label, candidate=name, finite=finite)
                        if finite:
                            diff = (value - reference).abs()
                            row.update(raw_mae=float(diff.mean()), raw_max=float(diff.max()),
                                       mae_over_reference_p2_p98=float(diff.mean() / scale),
                                       historical_raw_allclose=bool(torch.allclose(value, reference, atol=.001, rtol=.001)),
                                       mae_vs_product_fp32=float((value - control_value).abs().mean()))
                        report['cases'].append(row)
                for name in ('FloorballGame', 'OfficeWalk', 'ParkingGarage'):
                    for index, rgb in enumerate(PublicFrames(name, 60)):
                        compare(rgb, f'{name}-{index}')
                    print(f'Compared {name}', flush=True)
                    save()
                for level in (0, 127, 255):
                    compare(np.full((1080, 1920, 3), level, np.uint8), f'constant-{level}')
                for width, height in ((2560, 1080), (1080, 1920), (3840, 2160)):
                    compare(cv2.resize(first, (width, height)), f'resized-{width}x{height}')
                control.stream.synchronize()
            report['completed'] = True
    except BaseException:
        report['error'] = traceback.format_exc()
        raise
    finally:
        save()
        print(str(args.output / 'report.json'), flush=True)


if __name__ == '__main__':
    main()
