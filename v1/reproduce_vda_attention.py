"""Extract real Q/K/V inputs and test the original attention subgraph."""
import argparse
import json
import os
import sys
import uuid

import cv2
import numpy as np
import onnx
import onnxruntime as ort
import torch

from vda_streaming_experiment import ROOT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--subgraph')
    parser.add_argument('--opt-level', type=int, default=3)
    args = parser.parse_args()
    dll = os.add_dll_directory('C:/TensorRT/TensorRT-11.2.1.2/bin')
    sys.path.append(str(ROOT/'out/v1-python-deps'))
    import tensorrt as trt
    root = ROOT/'out/vda-attention-repro'/uuid.uuid4().hex
    root.mkdir(parents=True)
    source = ROOT/'out/vda-onnx-spike/164ea87e20e54fba91149f398dc1f047/warmup.onnx'
    prefix='/head/motion_modules.2/temporal_transformer/transformer_blocks.0/attention_blocks.0/'
    names=[prefix+f'to_{name}/MatMul_output_0' for name in ('q','k','v')]
    final=prefix+'Reshape_11_output_0'
    report=dict(passed=False, inputs=[], results=[])
    try:
        model=onnx.shape_inference.infer_shapes(onnx.load(str(source)))
        values={item.name:item for item in [*model.graph.value_info,*model.graph.output,*model.graph.input]}
        for name in names:
            model.graph.output.append(values[name])
        onnx.save(model,str(root/'observed.onnx'))
        cap=cv2.VideoCapture(args.input)
        try:
            ok,frame=cap.read()
            if not ok: raise RuntimeError('Input unreadable')
        finally: cap.release()
        frame=cv2.resize(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB),(252,140)).astype(np.float32)/255
        frame=(frame-np.array([.485,.456,.406],np.float32))/np.array([.229,.224,.225],np.float32)
        image=frame.transpose(2,0,1).copy()[None,None]
        options=ort.SessionOptions(); options.intra_op_num_threads=4
        full=ort.InferenceSession(str(root/'observed.onnx'),options,providers=['CPUExecutionProvider'])
        inputs=dict(zip(names,full.run(names,{'image':image})))
        report['inputs']=[dict(name=k,shape=list(v.shape),finite=bool(np.isfinite(v).all())) for k,v in inputs.items()]
        np.savez(root/'inputs.npz',**{f'input_{i}':v for i,v in enumerate(inputs.values())})
        onnx.utils.extract_model(str(source),str(root/'attention.onnx'),names,[final])
        if args.subgraph:
            from pathlib import Path
            (root/'attention.onnx').write_bytes(Path(args.subgraph).read_bytes())
        reference=ort.InferenceSession(str(root/'attention.onnx'),options,providers=['CPUExecutionProvider']).run(None,inputs)[0]
        logger=trt.Logger(trt.Logger.WARNING)
        builder=trt.Builder(logger); network=builder.create_network(0); reader=trt.OnnxParser(network,logger)
        assert reader.parse_from_file(str(root/'attention.onnx'))
        config=builder.create_builder_config(); config.clear_flag(trt.BuilderFlag.TF32)
        config.builder_optimization_level=args.opt_level
        report['builder_optimization_level']=args.opt_level
        config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE,2*1024**3)
        payload=builder.build_serialized_network(network,config)
        if payload is None: raise RuntimeError('Subgraph build failed')
        (root/'attention.plan').write_bytes(bytes(payload))
        runtime=trt.Runtime(logger); engine=runtime.deserialize_cuda_engine(payload); context=engine.create_execution_context()
        buffers={k:torch.from_numpy(v).cuda().contiguous() for k,v in inputs.items()}
        buffers[final]=torch.empty(tuple(engine.get_tensor_shape(final)),device='cuda')
        for name,tensor in buffers.items(): assert context.set_tensor_address(name,tensor.data_ptr())
        stream=torch.cuda.Stream()
        stream.wait_stream(torch.cuda.current_stream())
        assert context.execute_async_v3(stream.cuda_stream)
        stream.synchronize()
        actual=buffers[final].cpu().numpy()
        finite=bool(np.isfinite(actual).all())
        report['results'].append(dict(ort_nonfinite=int(np.count_nonzero(~np.isfinite(reference))),
            trt_nonfinite=int(np.count_nonzero(~np.isfinite(actual))),
            max_abs=float(np.max(np.abs(actual-reference))) if finite else None))
        report['passed']=finite and bool(np.allclose(actual,reference,atol=1e-3,rtol=1e-3))
    finally:
        (root/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report,indent=2)); print(root/'report.json')
        dll.close()


if __name__=='__main__': main()
