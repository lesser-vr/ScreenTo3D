# oVDA derivative precision experiment, NC-SA-UHDV1.0; see LICENSE/README.md.
"""Build isolated c16 mixed-precision candidates from a pinned verified export."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time

SOURCE = '586a7ca21a7d91360e4e2b52912685875e50f07cd18a42ed34a13e529f4ba545'
LOW_SOURCE = '6a80992ced60e7eed21ff300bf714c97737b8e316ffb66d436fb41a18a5a4104'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path('out/ovda-trt/bb6a03e172414a60b470f70c2cfd9a98/model.onnx'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, default=Path('C:/TensorRT/TensorRT-11.2.1.2/bin'))
    parser.add_argument('--control-only',action='store_true')
    parser.add_argument('--low-resolution',action='store_true',help='Use the locally exported/pinned 392x700 c16 graph')
    parser.add_argument('--spatial-only',action='store_true',help='Build only encoder+spatial mixed FP16')
    args = parser.parse_args()
    if args.low_resolution:args.source=Path('out/ovda-resolution-20261109/low-fp32/model.onnx')
    payload = args.source.read_bytes()
    source_pin=LOW_SOURCE if args.low_resolution else SOURCE
    if hashlib.sha256(payload).hexdigest() != source_pin:
        raise ValueError('Expected the verified c16 FP32 export')
    if args.control_only and args.spatial_only:parser.error('Control and spatial-only are exclusive')
    from build_vda_mixed_fp16 import lower_encoder
    from build_vda_spatial_trial import spatial_graph
    import onnx
    with os.add_dll_directory(str(args.runtime.resolve(strict=True))):
        import tensorrt as trt
        if trt.__version__ != '11.2.1.2':
            raise ValueError('Unexpected TensorRT version')
        args.output.mkdir(parents=True, exist_ok=False)
        encoder = None if args.control_only else lower_encoder(payload)
        variants=(('fp32-current',payload),) if args.control_only else ((('encoder-spatial',spatial_graph(encoder)),) if args.spatial_only else (('encoder',encoder),('encoder-spatial',spatial_graph(encoder))))
        for name, graph in variants:
            folder = args.output/name
            folder.mkdir()
            (folder/'model.onnx').write_bytes(graph)
            logger = trt.Logger(trt.Logger.WARNING)
            builder = trt.Builder(logger)
            network = builder.create_network(0)
            reader = trt.OnnxParser(network, logger)
            if not reader.parse(graph):
                raise ValueError([str(reader.get_error(i)) for i in range(reader.num_errors)])
            config = builder.create_builder_config()
            config.clear_flag(trt.BuilderFlag.TF32)
            config.profiling_verbosity = trt.ProfilingVerbosity.DETAILED
            config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, 2*1024**3)
            print('Building', name, flush=True)
            started = time.monotonic()
            serialized = builder.build_serialized_network(network, config)
            if serialized is None:
                raise RuntimeError('TensorRT trial build failed')
            plan = bytes(serialized)
            (folder/'model.plan').write_bytes(plan)
            runtime = trt.Runtime(logger)
            engine = runtime.deserialize_cuda_engine(plan)
            inspection = engine.create_engine_inspector().get_engine_information(trt.LayerInformationFormat.JSON)
            (folder/'inspector.json').write_text(inspection, encoding='utf-8')
            record = dict(candidate=name, source_graph_sha256=source_pin,
                          graph_sha256=hashlib.sha256(graph).hexdigest(),
                          plan_sha256=hashlib.sha256(plan).hexdigest(), bytes=len(plan),
                          build_seconds=time.monotonic()-started,
                          precision='FP32' if args.control_only else ('mixed FP16 encoder+spatial; FP32 temporal/cache/head/I/O' if name=='encoder-spatial' else 'mixed FP16 encoder; FP32 temporal/cache/head/I/O'),
                          shape=[1,1,3,392,700] if args.low_resolution else [1,1,3,518,924], license='NC-SA-UHDV1.0',
                          io=[dict(name=engine.get_tensor_name(i),
                                   shape=list(engine.get_tensor_shape(engine.get_tensor_name(i))),
                                   dtype=str(engine.get_tensor_dtype(engine.get_tensor_name(i))))
                              for i in range(engine.num_io_tensors)],
                          half_initializers=sum(t.data_type == onnx.TensorProto.FLOAT16
                                                for t in onnx.load_from_string(graph).graph.initializer))
            (folder/'trial.json').write_text(json.dumps(record, indent=2))
            print(json.dumps(dict(candidate=name, build_seconds=record['build_seconds'], bytes=len(plan))), flush=True)
            del engine, runtime, serialized, config, reader, network, builder


if __name__ == '__main__':
    main()
