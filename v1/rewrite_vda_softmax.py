"""Experimental stable Softmax decomposition; original ONNX stays untouched."""
import argparse
import hashlib
import json
from pathlib import Path
import uuid
import onnx
from onnx import helper, TensorProto
from vda_streaming_experiment import ROOT


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('source',type=Path)
    args=parser.parse_args()
    root=ROOT/'out/vda-softmax-rewrite'/uuid.uuid4().hex
    root.mkdir(parents=True)
    report=[]
    for path in sorted(args.source.glob('*.onnx')):
        if path.name not in ('warmup.onnx','cached.onnx','attention.onnx'): continue
        model=onnx.load(str(path))
        nodes=[]; count=0
        for node in model.graph.node:
            if node.op_type!='Softmax' or 'motion_modules.' not in node.name:
                nodes.append(node); continue
            axis=next((a.i for a in node.attribute if a.name=='axis'),-1)
            prefix=node.output[0]+'/stable'
            axes=prefix+'/axes'
            model.graph.initializer.append(helper.make_tensor(axes,TensorProto.INT64,[1],[axis]))
            nodes.extend([
                helper.make_node('ReduceMax',[node.input[0]],[prefix+'/max'],name=prefix+'/max',axes=[axis],keepdims=1),
                helper.make_node('Sub',[node.input[0],prefix+'/max'],[prefix+'/shift'],name=prefix+'/shift'),
                helper.make_node('Exp',[prefix+'/shift'],[prefix+'/exp'],name=prefix+'/exp'),
                helper.make_node('ReduceSum',[prefix+'/exp',axes],[prefix+'/sum'],name=prefix+'/sum',keepdims=1),
                helper.make_node('Div',[prefix+'/exp',prefix+'/sum'],list(node.output),name=prefix+'/divide')])
            count+=1
        del model.graph.node[:]; model.graph.node.extend(nodes)
        onnx.checker.check_model(model)
        onnx.save(model,str(root/path.name))
        report.append(dict(file=path.name,replaced=count,source_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    (root/'rewrite.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(root)


if __name__=='__main__': main()
