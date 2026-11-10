"""Pinned local ZipDepth export/parity experiment; never installs app defaults."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
UPSTREAM = ROOT / 'out/zipdepth-upstream'
OUT = ROOT / 'out/zipdepth-exact-20261106'
REVISION = '91f3fd21e131641f51e8d35736d1958350180e3a'
SHAPE = (384, 704)
sys.path[:0] = [str(UPSTREAM), str(ROOT / 'v1')]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    import cv2
    import numpy as np
    import torch
    import onnx
    import onnxruntime as ort
    from onnxruntime.transformers.float16 import convert_float_to_float16
    from public_test_media import PublicFrames, SOURCES
    from zipdepth.model.architecture import create_model
    from zipdepth.utils.model_utils import strip_state_dict_prefixes, fuse_remaining_conv_bn

    assert subprocess.check_output(['git', '-C', str(UPSTREAM), 'rev-parse', 'HEAD'], text=True).strip() == REVISION
    assert not subprocess.check_output(['git', '-C', str(UPSTREAM), 'status', '--porcelain'], text=True).strip()
    OUT.mkdir(exist_ok=False)
    torch.set_num_threads(4)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    checkpoint = UPSTREAM / 'checkpoints/zipdepth_base.pth'
    report = dict(completed=False, revision=REVISION, weights_sha256=sha(checkpoint),
                  torch=torch.__version__, gpu=torch.cuda.get_device_name(), shape=SHAPE,
                  source_hashes={str(p.relative_to(UPSTREAM)): sha(p) for p in UPSTREAM.rglob('*.py')}, cases=[])
    def save():
        (OUT / 'prepare.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    save()
    try:
        model = create_model(variant='base').eval()
        ckpt = torch.load(checkpoint, map_location='cpu', weights_only=True)
        state = strip_state_dict_prefixes(ckpt.get('model_state_dict', ckpt))
        model.load_state_dict(state, strict=True)
        fused = copy.deepcopy(model)
        fused.fuse_for_inference()
        fuse_remaining_conv_bn(fused)
        report['fused_parameters'] = sum(p.numel() for p in fused.parameters())
        export_model = copy.deepcopy(fused)
        # The upstream exporter replaces learned softmax-weighted global context
        # with a uniform average. Preserve the trained forward instead.
        with torch.inference_mode():
            torch.onnx.export(export_model, torch.zeros(1,3,*SHAPE), str(OUT/'fp32.onnx'),
                              input_names=['image'], output_names=['depth'], opset_version=17,
                              do_constant_folding=True, dynamo=False)
        report['export_recipe'] = 'fused original forward; no pooling/attention substitution'
        graph = convert_float_to_float16(onnx.load(OUT/'fp32.onnx'), keep_io_types=True,
                                        op_block_list=['Resize', 'Softmax', 'ReduceMean'])
        available = {x.name for x in graph.graph.input} | {x.name for x in graph.graph.initializer}
        pending, ordered = list(graph.graph.node), []
        while pending:
            ready = [n for n in pending if all(not i or i in available for i in n.input)]
            if not ready:
                raise ValueError('Cannot order FP16 graph')
            for n in ready:
                ordered.append(n); available.update(n.output); pending.remove(n)
        del graph.graph.node[:]
        graph.graph.node.extend(ordered)
        onnx.checker.check_model(graph)
        onnx.save(graph, OUT/'fp16.onnx')
        with os.add_dll_directory('C:/TensorRT/TensorRT-11.2.1.2/bin'):
            import tensorrt as trt
            assert trt.__version__ == '11.2.1.2'
            logger = trt.Logger(trt.Logger.WARNING)
            builder = trt.Builder(logger)
            network = builder.create_network(0)
            parser = trt.OnnxParser(network, logger)
            if not parser.parse_from_file(str(OUT/'fp16.onnx')):
                raise RuntimeError('\n'.join(str(parser.get_error(i)) for i in range(parser.num_errors)))
            config = builder.create_builder_config()
            config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, 2*1024**3)
            config.clear_flag(trt.BuilderFlag.TF32)
            began = time.monotonic()
            payload = builder.build_serialized_network(network, config)
            if payload is None:
                raise RuntimeError('TensorRT build failed')
            (OUT/'model.plan').write_bytes(bytes(payload))
            report.update(build_seconds=time.monotonic()-began, plan_sha256=sha(OUT/'model.plan'),
                          plan_bytes=(OUT/'model.plan').stat().st_size, tensorrt=trt.__version__)
            save()
            runtime = trt.Runtime(logger)
            engine = runtime.deserialize_cuda_engine(bytes(payload))
            context = engine.create_execution_context()
            report['io'] = {engine.get_tensor_name(i): list(engine.get_tensor_shape(engine.get_tensor_name(i))) for i in range(engine.num_io_tensors)}
            stream = torch.cuda.Stream()
            output = torch.empty(tuple(engine.get_tensor_shape('depth')), device='cuda', dtype=torch.float32)
            session_options = ort.SessionOptions(); session_options.intra_op_num_threads = 4
            session = ort.InferenceSession(str(OUT/'fp32.onnx'), session_options, providers=['CPUExecutionProvider'])
            for name in SOURCES:
                for index in (0, 59):
                    rgb = PublicFrames(name, 60)[index]
                    h, w = rgb.shape[:2]; s = min(SHAPE[0]/h, SHAPE[1]/w)
                    rh, rw = round(h*s), round(w*s)
                    y, x = (SHAPE[0]-rh)//2, (SHAPE[1]-rw)//2
                    image = cv2.resize(rgb, (rw,rh), interpolation=cv2.INTER_LINEAR)
                    image = cv2.copyMakeBorder(image,y,SHAPE[0]-rh-y,x,SHAPE[1]-rw-x,cv2.BORDER_REPLICATE)
                    array = np.ascontiguousarray(image.transpose(2,0,1)[None], dtype=np.float32)/255
                    with torch.inference_mode():
                        inp = torch.from_numpy(array)
                        reference = model(inp).numpy()
                        fused_out = fused(inp).numpy()
                        export_out = export_model(inp).numpy()
                        onnx_out = session.run(None, {'image':array})[0]
                        with torch.cuda.stream(stream):
                            gpu = inp.cuda()
                            context.set_tensor_address('image',gpu.data_ptr())
                            context.set_tensor_address('depth',output.data_ptr())
                            for _ in range(10):
                                assert context.execute_async_v3(stream.cuda_stream)
                            start, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
                            start.record(stream)
                            for _ in range(100):
                                assert context.execute_async_v3(stream.cuda_stream)
                            end.record(stream); stream.synchronize()
                            actual = output.cpu().numpy().copy()
                    row = dict(source=name, index=index, model_ms=start.elapsed_time(end)/100)
                    for label, result in [('fusion',fused_out),('export',export_out),('onnx',onnx_out),('fp16',actual)]:
                        diff = np.abs(result-reference)
                        span = max(float(np.percentile(reference,99)-np.percentile(reference,1)),1e-6)
                        row[label] = dict(mae=float(diff.mean()), max=float(diff.max()),
                                          span_normalized_mae=float(diff.mean()/span), finite=bool(np.isfinite(result).all()))
                    report['cases'].append(row); save()
            report['completed'] = True
            report['parity_pass'] = all(all(r[k]['finite'] and r[k]['span_normalized_mae'] < (.005 if k=='fp16' else .0001) for k in ('fusion','export','onnx','fp16')) for r in report['cases'])
            save()
            print(json.dumps({k:v for k,v in report.items() if k not in ('source_hashes','cases')},indent=2))
    except BaseException as exc:
        report['error'] = repr(exc); save(); raise

if __name__ == '__main__':
    main()
