"""Inspect and time the installed Small FP16 path without changing its model."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics

import numpy as np
import onnx
import torch

from screento3d_app.desktop_jobs import ROOT, BUNDLE
from screento3d_app.resources import configure_resource_root


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    configure_resource_root(BUNDLE)
    from screento3d_app.trt_backend import DepthEngine, _model_path, _engine_path, trt
    path = _model_path()
    pin = json.loads((ROOT / 'models/da2-small/model-manifest.json').read_text())
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != pin['onnx_sha256'] or path.stat().st_size != pin['onnx_bytes']:
        raise ValueError('Installed Small model differs from its manifest')
    graph = onnx.load(str(path))
    types = {x.name: x.type.tensor_type.elem_type for x in list(graph.graph.value_info) + list(graph.graph.input) + list(graph.graph.output)}
    types.update({x.name: x.data_type for x in graph.graph.initializer})
    report = dict(completed=False, model_sha256=digest, model_bytes=path.stat().st_size,
        initializer_types=dict(Counter(onnx.TensorProto.DataType.Name(x.data_type) for x in graph.graph.initializer)),
        compute_input_types=dict(Counter(n.op_type + ':' + onnx.TensorProto.DataType.Name(types.get(n.input[0], 0))
            for n in graph.graph.node if n.op_type in ('Conv', 'MatMul', 'Softmax'))),
        shape=[1, 3, 518, 518], license=pin['license'], tensorrt=trt.__version__,
        scope='existing Small engine, model-only CUDA timing; no new precision conversion or quality ranking')
    try:
        with DepthEngine() as engine:
            # A fixed resident input for model timing. Transfers are outside events.
            value = engine.infer(np.zeros((1, 3, 518, 518), np.float32))
            report['finite'] = bool(np.isfinite(value).all())
            report['io'] = {engine.engine.get_tensor_name(i): str(engine.engine.get_tensor_dtype(engine.engine.get_tensor_name(i))) for i in range(engine.engine.num_io_tensors)}
            stream = torch.cuda.ExternalStream(int(engine.stream))
            def run():
                if not engine.context.execute_async_v3(stream_handle=int(engine.stream)):
                    raise RuntimeError('Small engine execution failed')
            for _ in range(10):
                run()
            stream.synchronize()
            times = []
            for _ in range(60):
                a, b = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
                a.record(stream)
                run()
                b.record(stream)
                b.synchronize()
                times.append(a.elapsed_time(b))
            report['model_gpu_ms'] = dict(median=statistics.median(times), samples=times)
            engine_path = _engine_path()
            report['engine'] = dict(path=str(engine_path), sha256=hashlib.sha256(engine_path.read_bytes()).hexdigest(), bytes=engine_path.stat().st_size)
            inspector = engine.engine.create_engine_inspector()
            (args.output / 'layers.json').write_text(inspector.get_engine_information(trt.LayerInformationFormat.JSON), encoding='utf-8')
        report['completed'] = True
    finally:
        (args.output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps({key: value for key, value in report.items() if key != 'model_gpu_ms'}), flush=True)
        print(report.get('model_gpu_ms', {}).get('median'), flush=True)


if __name__ == '__main__':
    main()
