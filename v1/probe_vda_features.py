"""Default-size prefix graph ORT/TensorRT diagnostic."""
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
from vda_streaming_experiment import ROOT, VdaStreamingEngine


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',required=True)
    args=parser.parse_args()
    dll=os.add_dll_directory('C:/TensorRT/TensorRT-11.2.1.2/bin')
    sys.path.append(str(ROOT/'out/v1-python-deps'))
    import tensorrt as trt
    root=ROOT/'out/vda-feature-probe'/uuid.uuid4().hex
    root.mkdir(parents=True)
    source=ROOT/'out/vda-softmax-rewrite/b2a2bf2379684e35ad298b8ba21f1943/warmup.onnx'
    names=['/patch_embed/proj/Conv_output_0','/Resize_output_0','/Add_output_0',
           '/blocks.0/Add_output_0','/blocks.0/Add_1_output_0']
    report=dict(passed=False,comparisons=[])
    try:
        onnx.utils.extract_model(str(source),str(root/'prefix.onnx'),['image'],names)
        cap=cv2.VideoCapture(args.input)
        try:
            ok,bgr=cap.read()
            if not ok: raise RuntimeError('Input unreadable')
        finally: cap.release()
        rgb=cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB)
        with VdaStreamingEngine(input_size=518) as model:
            model.infer(rgb)
            array=model.model.transform({'image':rgb.astype(np.float32)/255})['image'].copy()[None,None]
        options=ort.SessionOptions(); options.intra_op_num_threads=4
        session=ort.InferenceSession(str(root/'prefix.onnx'),options,providers=['CPUExecutionProvider'])
        reference=session.run(names,{'image':array})
        logger=trt.Logger(trt.Logger.WARNING)
        builder=trt.Builder(logger); net=builder.create_network(0); reader=trt.OnnxParser(net,logger)
        assert reader.parse_from_file(str(root/'prefix.onnx'))
        config=builder.create_builder_config(); config.clear_flag(trt.BuilderFlag.TF32)
        config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE,2*1024**3)
        payload=builder.build_serialized_network(net,config)
        if payload is None: raise RuntimeError('Prefix build failed')
        runtime=trt.Runtime(logger); engine=runtime.deserialize_cuda_engine(payload); context=engine.create_execution_context()
        buffers={'image':torch.from_numpy(array).cuda()}
        for name in names:
            buffers[name]=torch.empty(tuple(engine.get_tensor_shape(name)),device='cuda',dtype=torch.float32)
        for name,value in buffers.items(): assert context.set_tensor_address(name,value.data_ptr())
        stream=torch.cuda.Stream(); stream.wait_stream(torch.cuda.current_stream())
        assert context.execute_async_v3(stream.cuda_stream)
        stream.synchronize()
        for name,expected in zip(names,reference):
            actual=buffers[name].cpu().numpy()
            finite=bool(np.isfinite(actual).all() and np.isfinite(expected).all())
            report['comparisons'].append(dict(name=name,finite=finite,
                max_abs=float(np.max(np.abs(actual-expected))) if finite else None,
                mean_abs=float(np.mean(np.abs(actual-expected))) if finite else None,
                passed=finite and bool(np.allclose(actual,expected,atol=1e-3,rtol=1e-3))))
        report['passed']=all(item['passed'] for item in report['comparisons'])
    finally:
        (root/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report,indent=2)); print(root/'report.json')
        dll.close()


if __name__=='__main__': main()
