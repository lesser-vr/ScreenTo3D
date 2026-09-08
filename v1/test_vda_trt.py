"""Experimental fixed-shape TensorRT/PyTorch parity on real-image inputs."""
import argparse
import hashlib
import json
import os
import sys
import time
import traceback
import uuid

import cv2
import numpy as np
import torch

from export_vda_spike import Step
from vda_streaming_experiment import ROOT, VdaStreamingEngine


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--frames', type=int, default=3)
    parser.add_argument('--input-size', type=int, choices=(140, 518), default=140)
    parser.add_argument('--input-width', type=int, choices=(896, 924), default=896)
    parser.add_argument('--plans', type=str)
    parser.add_argument('--probe', action='store_true')
    parser.add_argument('--onnx-dir', type=str, default='out/vda-onnx-spike/164ea87e20e54fba91149f398dc1f047')
    args = parser.parse_args()
    if not 3 <= args.frames <= 124:
        parser.error('frames must be 3..124 for this bounded diagnostic')
    if args.probe and args.plans:
        parser.error('Probe requires a fresh instrumented build')
    dll = os.add_dll_directory('C:/TensorRT/TensorRT-11.2.1.2/bin')
    sys.path.append(str(ROOT / 'out/v1-python-deps'))
    import tensorrt as trt
    root = ROOT / 'out/vda-trt-parity' / uuid.uuid4().hex
    root.mkdir(parents=True)
    source = ROOT / args.onnx_dir
    report = dict(passed=False, input=args.input, torch=torch.__version__, tensorrt=trt.__version__,
        input_size=args.input_size, preprocessing='upstream aspect preserving' if args.input_size == 518 else 'diagnostic resize',
        input_shape=[1, 1, 3, args.input_size, 252 if args.input_size == 140 else args.input_width],
        gpu=torch.cuda.get_device_name(), atol=1e-3, rtol=1e-3, builds=[], comparisons=[])
    logger = trt.Logger(trt.Logger.WARNING)
    runtime = trt.Runtime(logger)
    engines = {}
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    try:
        for name in ('warmup', 'cached'):
            builder = trt.Builder(logger)
            network = builder.create_network(0)
            reader = trt.OnnxParser(network, logger)
            path = source / f'{name}.onnx'
            if not reader.parse_from_file(str(path)):
                raise RuntimeError(str([str(reader.get_error(i)) for i in range(reader.num_errors)]))
            config = builder.create_builder_config()
            if args.probe:
                for layer_index in range(network.num_layers):
                    layer = network.get_layer(layer_index)
                    if ('motion_modules.2/temporal_transformer/transformer_blocks.0/' in layer.name
                        and any(part in layer.name for part in ('attention_blocks.0/', 'attention_blocks.1/', 'norms.1/'))):
                        for output_index in range(layer.num_outputs):
                            tensor = layer.get_output(output_index)
                            if tensor is not None and tensor.dtype == trt.float32 and not tensor.is_network_output:
                                network.mark_output(tensor)
            config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, 2 * 1024**3)
            config.clear_flag(trt.BuilderFlag.TF32)
            print('BUILD: ' + name, flush=True)
            start = time.perf_counter()
            serialized = (ROOT / args.plans / f'{name}.plan').read_bytes() if args.plans else builder.build_serialized_network(network, config)
            if serialized is None:
                raise RuntimeError('Build failed: ' + name)
            payload = bytes(serialized)
            (root / f'{name}.plan').write_bytes(payload)
            engine = runtime.deserialize_cuda_engine(payload)
            context = engine.create_execution_context()
            engines[name] = (engine, context)
            report['builds'].append(dict(name=name, seconds=time.perf_counter()-start,
                onnx_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                plan_sha256=hashlib.sha256(payload).hexdigest(), bytes=len(payload)))
            print('BUILT: ' + name, flush=True)

        def infer(name, inputs):
            engine, context = engines[name]
            outputs = {}
            for i in range(engine.num_io_tensors):
                key = engine.get_tensor_name(i)
                if engine.get_tensor_dtype(key) != trt.float32:
                    raise RuntimeError('Unexpected dtype: ' + key)
                if engine.get_tensor_mode(key) == trt.TensorIOMode.INPUT:
                    tensor = inputs[key]
                else:
                    tensor = torch.empty(tuple(engine.get_tensor_shape(key)), device='cuda', dtype=torch.float32)
                    outputs[key] = tensor
                assert tuple(tensor.shape) == tuple(engine.get_tensor_shape(key)) and tensor.is_contiguous()
                if not context.set_tensor_address(key, tensor.data_ptr()):
                    raise RuntimeError('Address rejected')
            if not context.execute_async_v3(torch.cuda.current_stream().cuda_stream):
                raise RuntimeError('Execution failed')
            torch.cuda.synchronize()
            if args.probe:
                report.setdefault('probes', []).append(dict(engine=name, outputs=[dict(name=key,
                    nonfinite=int((~torch.isfinite(value)).sum().item()),
                    shape=list(value.shape)) for key,value in outputs.items()]))
            return (outputs['depth'], *(outputs[f'new_cache_{i}'] for i in range(8)))

        capture = cv2.VideoCapture(args.input)
        frames = []
        transform = None
        try:
            for i in range(args.frames):
                ok, bgr = capture.read()
                if not ok:
                    raise RuntimeError('Need three real frames')
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                if args.input_size == 518:
                    if transform is None:
                        with VdaStreamingEngine(input_size=518) as preparation:
                            preparation.infer(rgb)
                            transform = preparation.model.transform
                    chw = transform({'image': rgb.astype(np.float32)/255})['image']
                    if chw.shape != (3,518,args.input_width):
                        raise ValueError('Source aspect ratio does not match the selected fixed profile')
                else:
                    rgb = cv2.resize(rgb, (252,140)).astype(np.float32)/255
                    rgb = (rgb-np.array([.485,.456,.406],np.float32))/np.array([.229,.224,.225],np.float32)
                    chw = rgb.transpose(2,0,1)
                frames.append(torch.from_numpy(chw.copy())[None,None].cuda())
        finally:
            capture.release()
        with VdaStreamingEngine(input_size=args.input_size) as oracle, torch.no_grad():
            step = Step(oracle.model).eval()
            histories = [[], []]
            for index, image in enumerate([*frames, frames[0]]):
                reset = index in (0, args.frames)
                if reset:
                    histories = [[], []]
                results = []
                for kind in range(2):
                    history = histories[kind]
                    cache = [] if reset else [torch.cat([h[j] for h in history[:2]+history[-29:]], dim=1).contiguous() for j in range(8)]
                    result = step(image, *cache) if kind == 0 else infer('warmup' if reset else 'cached',
                        dict(image=image, **{f'cache_{j}': value for j,value in enumerate(cache)}))
                    histories[kind] = [result[1:]]*32 if reset else history + [result[1:]]
                    if len(histories[kind]) > 42:
                        del histories[kind][1]
                    results.append(result)
                for j, (expected, actual) in enumerate(zip(*results)):
                    a, b = expected.cpu().numpy(), actual.cpu().numpy()
                    finite = bool(np.isfinite(a).all() and np.isfinite(b).all())
                    matches = finite and bool(np.allclose(a,b,rtol=1e-3,atol=1e-3))
                    report['comparisons'].append(dict(frame=index, tensor='depth' if j==0 else f'cache_{j-1}',
                        oracle_nonfinite=int(np.count_nonzero(~np.isfinite(a))), trt_nonfinite=int(np.count_nonzero(~np.isfinite(b))),
                        max_abs=float(np.max(np.abs(a-b))) if finite else None,
                        mean_abs=float(np.mean(np.abs(a-b))) if finite else None, passed=matches))
                print('COMPARED: ' + str(index), flush=True)
        report['passed'] = all(item['passed'] for item in report['comparisons'])
        if not report['passed']:
            raise RuntimeError('Numerical parity threshold failed; inspect report')
    except Exception:
        report['error'] = traceback.format_exc()
        raise
    finally:
        torch.cuda.synchronize()
        engines.clear()
        (root / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(root / 'report.json', flush=True)
        dll.close()


if __name__ == '__main__':
    main()
