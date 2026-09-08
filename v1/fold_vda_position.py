"""Fold input-independent positional Resize for a fixed-shape experiment."""
import argparse
import hashlib
import json
from pathlib import Path
import uuid
import onnx
import onnxruntime as ort
import numpy as np
from vda_streaming_experiment import ROOT


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('source',type=Path)
    args=parser.parse_args()
    root=ROOT/'out/vda-position-fold'/uuid.uuid4().hex
    root.mkdir(parents=True)
    report=[]
    for label in ('warmup','cached'):
        path=args.source/f'{label}.onnx'
        model=onnx.load(str(path))
        nodes={output:node for node in model.graph.node for output in node.output}
        target='/Resize_output_0'
        node=nodes[target]
        if node.op_type!='Resize': raise RuntimeError('Unexpected positional node')
        initializers={item.name for item in model.graph.initializer}
        visited=set()
        def check(value):
            if not value or value in initializers or value in visited: return
            visited.add(value)
            if value not in nodes: raise RuntimeError('Positional path depends on runtime input: '+value)
            for dependency in nodes[value].input: check(dependency)
        check(target)
        constant_path=root/f'{label}-position-only.onnx'
        constant_model=onnx.utils.Extractor(onnx.shape_inference.infer_shapes(model)).extract_model([],[target])
        onnx.checker.check_model(constant_model)
        onnx.save(constant_model,str(constant_path))
        session=ort.InferenceSession(str(constant_path),providers=['CPUExecutionProvider'])
        if session.get_inputs(): raise RuntimeError('Position is not constant')
        position=session.run([target],{})[0]
        if not np.isfinite(position).all(): raise RuntimeError('Nonfinite position')
        retained=[item for item in model.graph.node if target not in item.output]
        del model.graph.node[:]; model.graph.node.extend(retained)
        model.graph.initializer.append(onnx.numpy_helper.from_array(position,target))
        onnx.checker.check_model(model)
        onnx.save(model,str(root/f'{label}.onnx'))
        report.append(dict(graph=label,position_shape=list(position.shape),
            source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            position_sha256=hashlib.sha256(position.tobytes()).hexdigest(),provider='ORT CPU constant evaluation'))
    (root/'fold.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(root)


if __name__=='__main__': main()
