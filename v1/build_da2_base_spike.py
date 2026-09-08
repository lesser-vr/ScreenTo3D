"""Fresh fixed-profile DA2 Base FP32 export/build/parity; not an app artifact."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import traceback
import uuid
from unittest.mock import patch

import cv2
import numpy as np
import onnx
import torch

from da2_base_experiment import Da2BaseOracle, ROOT, validate_frame

SHAPE = (1, 3, 518, 896)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    global SHAPE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--frames', type=int, default=64)
    parser.add_argument('--width', type=int, choices=(896, 924), default=896)
    parser.add_argument('--precision', choices=('fp32', 'fp16', 'fp16-head'), default='fp32')
    parser.add_argument('--runtime-dir', type=Path, default=Path('C:/TensorRT/TensorRT-11.2.1.2/bin'))
    args = parser.parse_args()
    SHAPE = (1, 3, 518, args.width)
    if not 3 <= args.frames <= 124:
        parser.error('frames must be 3..124')
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA required; no fallback')
    root = ROOT/'out/da2-base-trt'/uuid.uuid4().hex
    root.mkdir(parents=True)
    print(root, flush=True)
    report = dict(passed=False, input_shape=SHAPE, precision=args.precision, tf32=False,
        atol=.001, rtol=.001, comparisons=[], input_sha256=digest(args.input),
        scope='Non-commercial development experiment, not app manifest or benchmark',
        torch=torch.__version__, cuda=torch.version.cuda, onnx=onnx.__version__,
        gpu=torch.cuda.get_device_name(), capability=torch.cuda.get_device_capability())
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    capture = cv2.VideoCapture(str(args.input))
    engine = context = runtime = None
    dll = os.add_dll_directory(str(args.runtime_dir.resolve(strict=True)))
    try:
        import tensorrt as trt
        report['tensorrt'] = trt.__version__
        if trt.__version__ != '11.2.1.2':
            raise RuntimeError('Experiment requires TensorRT 11.2.1.2')
        ok, first = capture.read()
        if not ok:
            raise ValueError('Missing first frame')
        validate_frame(cv2.cvtColor(first, cv2.COLOR_BGR2RGB))
        with Da2BaseOracle() as oracle, torch.inference_mode(), torch.autocast('cuda', enabled=False):
            report['provenance'] = oracle.telemetry()
            image, _ = oracle.model.image2tensor(first, 518)
            if tuple(image.shape) != SHAPE:
                raise ValueError('Source does not map to fixed 518x896 profile')
            original = oracle.model(image).clone()
            backbone = oracle.model.pretrained
            tokens = torch.zeros((1, (518//14)*(args.width//14)+1, backbone.embed_dim), device='cuda')
            position = backbone.interpolate_pos_encoding(tokens, 518, args.width).detach().clone()
            backbone.register_buffer('_export_fixed_position', position)
            try:
                with patch.object(backbone, 'interpolate_pos_encoding',
                                  side_effect=lambda x, w, h: backbone._export_fixed_position.to(x.dtype)):
                    torch.testing.assert_close(oracle.model(image), original, atol=0, rtol=0)
                    report['position_fold_exact'] = True
                    torch.onnx.export(oracle.model, (image,), str(root/'model.onnx'),
                        opset_version=17, dynamo=False, input_names=['image'], output_names=['depth'])
            finally:
                del backbone._export_fixed_position
            del original, tokens, position
            onnx.checker.check_model(str(root/'model.onnx'))
            if args.precision != 'fp32':
                from onnxruntime.transformers.float16 import convert_float_to_float16
                source_graph = onnx.load(str(root/'model.onnx'))
                blocked = [n.name for n in source_graph.graph.node if '/depth_head/' not in n.name] if args.precision == 'fp16-head' else []
                graph = convert_float_to_float16(source_graph, keep_io_types=True,
                    op_block_list=['Resize', 'LayerNormalization', 'Softmax'], node_block_list=blocked)
                pending = list(graph.graph.node)
                known = {v.name for v in graph.graph.input} | {v.name for v in graph.graph.initializer}
                ordered = []
                while pending:
                    ready = [n for n in pending if all(not key or key in known for key in n.input)]
                    if not ready:
                        raise ValueError('FP16 graph contains unresolved inputs or a cycle')
                    for node in ready:
                        ordered.append(node)
                        known.update(node.output)
                        pending.remove(node)
                del graph.graph.node[:]
                graph.graph.node.extend(ordered)
                onnx.checker.check_model(graph)
                onnx.save(graph, str(root/'model.onnx'))
                report['fp16_policy'] = ('FP32 encoder; FP16 eligible depth head ops' if args.precision == 'fp16-head' else 'FP16 eligible graph ops') + '; FP32 I/O, Resize, LayerNormalization and Softmax'
            report['onnx_sha256'] = digest(root/'model.onnx')
            print('EXPORTED: fixed-position '+args.precision+' graph', flush=True)
            logger = trt.Logger(trt.Logger.WARNING)
            builder = trt.Builder(logger)
            network = builder.create_network(0)
            reader = trt.OnnxParser(network, logger)
            if not reader.parse_from_file(str(root/'model.onnx')):
                raise RuntimeError('\n'.join(str(reader.get_error(i)) for i in range(reader.num_errors)))
            config = builder.create_builder_config()
            config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, 2*1024**3)
            config.clear_flag(trt.BuilderFlag.TF32)
            start = time.perf_counter()
            print('BUILD: '+args.precision+', TF32 disabled', flush=True)
            serialized = builder.build_serialized_network(network, config)
            if serialized is None:
                raise RuntimeError('TensorRT build failed')
            (root/'model.plan').write_bytes(bytes(serialized))
            report['build_seconds'] = time.perf_counter()-start
            report['plan_sha256'] = digest(root/'model.plan')
            del serialized, config, reader, network, builder
            runtime = trt.Runtime(logger)
            engine = runtime.deserialize_cuda_engine((root/'model.plan').read_bytes())
            if engine is None:
                raise RuntimeError('Plan deserialization failed')
            expected_io = {'image': (trt.TensorIOMode.INPUT, SHAPE),
                           'depth': (trt.TensorIOMode.OUTPUT, (1, 518, args.width))}
            if engine.num_io_tensors != 2:
                raise ValueError('Unexpected engine bindings')
            for i in range(engine.num_io_tensors):
                name = engine.get_tensor_name(i)
                if (name not in expected_io or engine.get_tensor_dtype(name) != trt.float32 or
                    (engine.get_tensor_mode(name), tuple(engine.get_tensor_shape(name))) != expected_io[name]):
                    raise ValueError('Unexpected tensor signature')
            context = engine.create_execution_context()
            if context is None:
                raise RuntimeError('Context creation failed')
            output = torch.empty((1, 518, args.width), device='cuda', dtype=torch.float32)

            def compare(bgr, label):
                validate_frame(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
                tensor, _ = oracle.model.image2tensor(bgr, 518)
                if tuple(tensor.shape) != SHAPE or not tensor.is_contiguous():
                    raise ValueError('Comparison shape/layout changed')
                expected = oracle.model(tensor)
                if not context.set_tensor_address('image', tensor.data_ptr()) or not context.set_tensor_address('depth', output.data_ptr()):
                    raise RuntimeError('Tensor address rejected')
                if not context.execute_async_v3(torch.cuda.current_stream().cuda_stream):
                    raise RuntimeError('TRT execution failed')
                torch.cuda.synchronize()  # Both bound buffers remain alive through completion.
                a, b = expected.cpu().numpy(), output.cpu().numpy()
                finite = bool(np.isfinite(a).all() and np.isfinite(b).all())
                passed = finite and bool(np.allclose(a, b, atol=.001, rtol=.001))
                report['comparisons'].append(dict(label=label, passed=passed, finite=finite,
                    max_abs=float(np.abs(a-b).max()) if finite else None,
                    mean_abs=float(np.abs(a-b).mean()) if finite else None))
                if label == 'frame-0':
                    np.savez_compressed(root/'first-frame-golden.npz', expected=a, actual=b)
                print('COMPARED: '+label+(' PASS' if passed else ' FAIL'), flush=True)

            compare(first, 'frame-0')
            for index in range(1, args.frames):
                ok, bgr = capture.read()
                if not ok:
                    raise ValueError('Input shorter than requested frame count')
                compare(bgr, f'frame-{index}')
            compare(first, 'repeated-first')
            compare(np.zeros_like(first), 'synthetic-black')
            compare(np.full_like(first, 127), 'synthetic-gray')
            green = np.zeros_like(first)
            green[:, :, 1] = 255
            compare(green, 'synthetic-green')
            if digest(args.input) != report['input_sha256']:
                raise ValueError('Input changed during experiment')
            report['passed'] = all(item['passed'] for item in report['comparisons'])
            if not report['passed']:
                raise RuntimeError('Numerical parity gate failed')
    except Exception:
        report['error'] = traceback.format_exc()
        raise
    finally:
        capture.release()
        try:
            torch.cuda.synchronize()
        finally:
            context = engine = runtime = None
            dll.close()
            (root/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            print(root/'report.json', flush=True)


if __name__ == '__main__':
    main()
