"""TensorRT parser probe only; does not build or run an engine."""
import argparse
import json
import os
from pathlib import Path
import tensorrt as trt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--runtime-dir', type=Path)
    args = parser.parse_args()
    dll_handle = os.add_dll_directory(str(args.runtime_dir.resolve(strict=True))) if args.runtime_dir else None
    report = dict(tensorrt=trt.__version__, build_attempted=False, graphs=[])
    logger = trt.Logger(trt.Logger.WARNING)
    for name in ('warmup', 'cached'):
        builder = trt.Builder(logger)
        network = builder.create_network(0)
        reader = trt.OnnxParser(network, logger)
        accepted = reader.parse_from_file(str(args.directory / f'{name}.onnx'))
        report['graphs'].append(dict(name=name, parsed=accepted,
            errors=[str(reader.get_error(i)) for i in range(reader.num_errors)],
            inputs=network.num_inputs, outputs=network.num_outputs))
    report['passed'] = all(g['parsed'] for g in report['graphs'])
    (args.directory / 'tensorrt-parser.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    if dll_handle is not None:
        dll_handle.close()
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
