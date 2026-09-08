# oVDA export/cache adaptation, NC-SA-UHDV1.0; see README.md and LICENSE.
"""Fixed 518x924 FP32 c16 ONNX/TRT spike, self-fed cache parity across 32 frames."""
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
import torch
import onnx
from oracle import ROOT, OvdaOracle, schedule, REVISION, WEIGHT_HASH


def digest(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()


def advance(cache, new, used):
    if used == 15:
        return {k: torch.cat([v[:,:,:,1:15,:], new[k], torch.zeros_like(new[k])], dim=3) for k,v in cache.items()}
    for k in cache: cache[k][:,:,:,used,:] = new[k][:,:,:,0,:]
    return cache


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--fold-position', action='store_true')
    parser.add_argument('--width', type=int, choices=(686, 896, 924), default=924)
    parser.add_argument('--precision', choices=('fp32','fp16'), default='fp32')
    parser.add_argument('--runtime-dir', type=Path, default=Path('C:/TensorRT/TensorRT-11.2.1.2/bin'))
    args = parser.parse_args()
    width = args.width
    root = ROOT/'out/ovda-trt'/uuid.uuid4().hex
    root.mkdir(parents=True)
    print(root, flush=True)
    report = dict(passed=False, source_revision=REVISION, weight_sha256=WEIGHT_HASH,
                  precision=args.precision, input_shape=[1,1,3,518,width], comparisons=[],
                  input_sha256=digest(args.input), fixes=[], license='NC-SA-UHDV1.0')
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    capture = cv2.VideoCapture(str(args.input))
    dll = os.add_dll_directory(str(args.runtime_dir.resolve(strict=True)))
    engine = context = runtime = None
    try:
        import tensorrt as trt
        if trt.__version__!='11.2.1.2':raise RuntimeError('Validated build procedure requires TensorRT 11.2.1.2')
        report.update(tensorrt=trt.__version__, torch=torch.__version__, gpu=torch.cuda.get_device_name(),
                      compute_capability=torch.cuda.get_device_capability(), cuda=torch.version.cuda, onnx=onnx.__version__)
        with OvdaOracle() as oracle, torch.inference_mode():
            model = oracle.model
            cache = model.setup_cache(518,width,'cuda')
            image = torch.zeros((1,1,3,518,width),device='cuda')
            mask, pos = schedule(0)
            mask = torch.tensor(mask,device='cuda'); pos = torch.tensor(pos,device='cuda')
            inputs = ['image', *['cache_'+k for k in cache], 'mask', 'position']
            outputs = ['depth', *['new_'+k for k in cache]]
            def export():
                torch.onnx.export(model,(image,cache,mask,pos),str(root/'model.onnx'),
                    input_names=inputs, output_names=outputs, opset_version=18, dynamo=False,
                    export_params=True, do_constant_folding=True)
            if args.fold_position:
                backbone = model.pretrained
                original = model(image,cache,mask,pos)
                tokens = torch.zeros((1,37*(width//14)+1,backbone.embed_dim),device='cuda')
                position = backbone.interpolate_pos_encoding(tokens,518,width).detach().clone()
                backbone.register_buffer('_export_position',position)
                try:
                    with patch.object(backbone,'interpolate_pos_encoding',
                                      side_effect=lambda x,w,h:backbone._export_position.to(x.dtype)):
                        torch.testing.assert_close(model(image,cache,mask,pos),original,atol=0,rtol=0)
                        export()
                finally:
                    del backbone._export_position
                report['fixes'].append('exact fixed-profile original positional interpolation buffer')
            else:
                export()
            onnx.checker.check_model(str(root/'model.onnx'))
            if args.precision=='fp16':
                from onnxruntime.transformers.float16 import convert_float_to_float16
                graph=convert_float_to_float16(onnx.load(str(root/'model.onnx')),keep_io_types=True,
                    op_block_list=['Resize','LayerNormalization','Softmax'])
                pending=list(graph.graph.node);ordered=[]
                known={v.name for v in graph.graph.input}|{v.name for v in graph.graph.initializer}
                while pending:
                    ready=[n for n in pending if all(not key or key in known for key in n.input)]
                    if not ready:raise ValueError('FP16 graph has unresolved inputs or cycle')
                    for node in ready:
                        ordered.append(node);known.update(node.output);pending.remove(node)
                del graph.graph.node[:]
                graph.graph.node.extend(ordered)
                onnx.checker.check_model(graph)
                onnx.save(graph,str(root/'model.onnx'))
                report['fp16_policy']='FP16 eligible ops; FP32 I/O, Resize, LayerNormalization, Softmax; no automatic promotion'
            report['onnx_sha256'] = digest(root/'model.onnx')
            print('PASS ONNX structural check; building TensorRT', flush=True)
            logger = trt.Logger(trt.Logger.WARNING)
            builder = trt.Builder(logger)
            network = builder.create_network(0)
            reader = trt.OnnxParser(network,logger)
            if not reader.parse_from_file(str(root/'model.onnx')):
                raise RuntimeError('\n'.join(str(reader.get_error(i)) for i in range(reader.num_errors)))
            config = builder.create_builder_config()
            config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE,2*1024**3)
            config.clear_flag(trt.BuilderFlag.TF32)
            start = time.perf_counter()
            serialized = builder.build_serialized_network(network,config)
            if serialized is None: raise RuntimeError('TensorRT build failed')
            (root/'model.plan').write_bytes(bytes(serialized))
            report.update(build_seconds=time.perf_counter()-start, plan_sha256=digest(root/'model.plan'))
            del serialized, config, reader, network, builder
            runtime = trt.Runtime(logger)
            engine = runtime.deserialize_cuda_engine((root/'model.plan').read_bytes())
            if engine is None: raise RuntimeError('Engine load failed')
            context = engine.create_execution_context()
            if context is None: raise RuntimeError('Context creation failed')
            report['io'] = [{ 'name':engine.get_tensor_name(i),
                'shape':list(engine.get_tensor_shape(engine.get_tensor_name(i))),
                'dtype':str(engine.get_tensor_dtype(engine.get_tensor_name(i))),
                'mode':str(engine.get_tensor_mode(engine.get_tensor_name(i)))} for i in range(engine.num_io_tensors)]
            assert set(inputs+outputs) == {i['name'] for i in report['io']}
            reference_cache = model.setup_cache(518,width,'cuda')
            trt_cache = model.setup_cache(518,width,'cuda')
            used = 0
            for index in range(32):
                ok,bgr = capture.read()
                if not ok: raise ValueError('Need 32 input frames')
                image = oracle.pre.preprocess(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB)).cuda().contiguous()
                if tuple(image.shape) != (1,1,3,518,width): raise ValueError('Fixed shape mismatch')
                mask,position = schedule(used)
                mask=torch.tensor(mask,device='cuda'); position=torch.tensor(position,device='cuda')
                expected,new_reference = model(image,reference_cache,mask,position)
                bindings = {'image':image,'mask':mask,'position':position,**{'cache_'+k:v for k,v in trt_cache.items()}}
                actual = {}
                for item in report['io']:
                    name = item['name']
                    if name not in bindings:
                        if engine.get_tensor_dtype(name) != trt.float32: raise ValueError('Unexpected output precision')
                        actual[name] = torch.empty(tuple(item['shape']),device='cuda',dtype=torch.float32)
                        bindings[name] = actual[name]
                    if list(bindings[name].shape) != item['shape']: raise ValueError('Unexpected tensor shape')
                    if not context.set_tensor_address(name,bindings[name].data_ptr()): raise RuntimeError('Binding rejected')
                if not context.execute_async_v3(torch.cuda.current_stream().cuda_stream): raise RuntimeError('Execution failed')
                torch.cuda.synchronize()
                reference = {'depth':expected,**{'new_'+k:v for k,v in new_reference.items()}}
                row = dict(frame=index, tensors={})
                for name, tensor in reference.items():
                    a,b = tensor.cpu().numpy(),actual[name].cpu().numpy()
                    finite = bool(np.isfinite(a).all() and np.isfinite(b).all())
                    row['tensors'][name] = dict(finite=finite, passed=finite and bool(np.allclose(a,b,atol=.001,rtol=.001)),
                        max_abs=float(np.abs(a-b).max()) if finite else None)
                report['comparisons'].append(row)
                print('COMPARED',index,all(v['passed'] for v in row['tensors'].values()),flush=True)
                if index == 0: np.savez_compressed(root/'golden-first.npz',reference=expected.cpu().numpy(),actual=actual['depth'].cpu().numpy())
                reference_cache = advance(reference_cache,new_reference,used)
                trt_cache = advance(trt_cache,{k:actual['new_'+k] for k in trt_cache},used)
                used=min(used+1,15)
            report['passed'] = all(t['passed'] for r in report['comparisons'] for t in r['tensors'].values())
            if not report['passed']: raise RuntimeError('Numerical parity gate failed; no engine promotion')
    except Exception:
        report['error'] = traceback.format_exc()
        raise
    finally:
        capture.release()
        torch.cuda.synchronize()
        context=engine=runtime=None
        dll.close()
        (root/'report.json').write_text(json.dumps(report,indent=2))
        print(root/'report.json',flush=True)


if __name__ == '__main__': main()
