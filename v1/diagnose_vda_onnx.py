"""Offline CPU ONNX reference diagnostic, never application fallback."""
import argparse
import json
import uuid
import cv2
import numpy as np
import onnx
import onnxruntime as ort
import torch
from export_vda_spike import Step
from vda_streaming_experiment import ROOT, VdaStreamingEngine


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--input-size', type=int, choices=(140,518), default=140)
    parser.add_argument('--onnx', default='out/vda-onnx-spike/164ea87e20e54fba91149f398dc1f047/warmup.onnx')
    args = parser.parse_args()
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    root = ROOT / 'out/vda-nan-diagnosis' / uuid.uuid4().hex
    root.mkdir(parents=True)
    source = ROOT / args.onnx
    report = dict(onnxruntime=ort.__version__, provider='CPUExecutionProvider', constants=[], outputs=[])
    report.update(input_size=args.input_size, source=str(source))
    try:
        model = onnx.load(str(source))
        tensors = [(item.name, item) for item in model.graph.initializer]
        for node in model.graph.node:
            for attribute in node.attribute:
                if attribute.type == onnx.AttributeProto.TENSOR:
                    tensors.append((node.name, attribute.t))
        for name, tensor in tensors:
            array = onnx.numpy_helper.to_array(tensor)
            if np.issubdtype(array.dtype, np.floating) and not np.isfinite(array).all():
                report['constants'].append(dict(name=name, shape=list(array.shape), nonfinite=int(np.count_nonzero(~np.isfinite(array)))))
        cap = cv2.VideoCapture(args.input)
        try:
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError('Input unreadable')
        finally:
            cap.release()
        rgb = cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)
        if args.input_size == 518:
            with VdaStreamingEngine(input_size=518) as preparation:
                preparation.infer(rgb)
                chw=preparation.model.transform({'image':rgb.astype(np.float32)/255})['image']
            image=chw.copy()[None,None]
        else:
            frame = cv2.resize(rgb,(252,140)).astype(np.float32)/255
            frame = (frame-np.array([.485,.456,.406],np.float32))/np.array([.229,.224,.225],np.float32)
            image = frame.transpose(2,0,1).copy()[None,None]
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        session = ort.InferenceSession(str(source), options, providers=['CPUExecutionProvider'])
        actual = session.run(None, {'image':image})
        with VdaStreamingEngine(input_size=args.input_size) as engine, torch.no_grad():
            expected = Step(engine.model)(torch.from_numpy(image).cuda())
            for output, a, b in zip(session.get_outputs(), actual, expected):
                b=b.cpu().numpy()
                finite=bool(np.isfinite(a).all() and np.isfinite(b).all())
                report['outputs'].append(dict(name=output.name, ort_nonfinite=int(np.count_nonzero(~np.isfinite(a))),
                    torch_nonfinite=int(np.count_nonzero(~np.isfinite(b))),
                    max_abs=float(np.max(np.abs(a-b))) if finite else None,
                    passed=finite and bool(np.allclose(a,b,rtol=1e-3,atol=1e-3))))
        report['passed'] = all(item['passed'] for item in report['outputs'])
    finally:
        (root/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report,indent=2),flush=True)
        print(root/'report.json',flush=True)


if __name__ == '__main__':
    main()
