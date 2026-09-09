"""Isolated DA2 Small shape A/B; does not change the app or certify VR quality."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import time

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SHAPES = ((518, 518), (392, 700))


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def preprocess(frame, shape):
    if shape not in SHAPES:
        raise ValueError('Unreviewed shape')
    if (not isinstance(frame, np.ndarray) or frame.dtype != np.uint8
            or frame.ndim != 3 or frame.shape[2] != 3):
        raise ValueError('Expected uint8 RGB')
    resized = cv2.resize(frame, (shape[1], shape[0]), interpolation=cv2.INTER_CUBIC)
    rgb = resized.astype(np.float32).transpose(2, 0, 1) / 255.0
    mean = np.array([.485, .456, .406], dtype=np.float32)[:, None, None]
    std = np.array([.229, .224, .225], dtype=np.float32)[:, None, None]
    return np.ascontiguousarray(((rgb - mean) / std)[None])


def comparison(reference, actual):
    if reference.shape != actual.shape or not (np.isfinite(reference).all()
                                               and np.isfinite(actual).all()):
        raise ValueError('Invalid oracle output')
    error = actual - reference
    absolute = np.abs(error)
    values = dict(mae=float(absolute.mean()), rmse=float(np.sqrt((error**2).mean())),
                  maximum=float(absolute.max()),
                  relative=float((absolute / np.maximum(np.abs(reference), 1e-6)).mean()),
                  correlation=float(np.corrcoef(reference.ravel(), actual.ravel())[0, 1]))
    values['passed'] = (values['mae'] <= .01 and values['rmse'] <= .015
                        and values['maximum'] <= .05 and values['relative'] <= .01
                        and values['correlation'] >= .999)
    return values


class Engine:
    def __init__(self, path, shape, trt, torch, logger):
        self.torch = torch
        self.stream = self.input = self.output = self.start = self.end = None
        self.context = self.engine = self.runtime = None
        try:
            self._initialize(path, shape, trt, torch, logger)
        except BaseException as primary:
            try:
                self.close()
            except Exception as cleanup:
                primary.add_note(f'Cleanup failed: {cleanup!r}')
            raise

    def _initialize(self, path, shape, trt, torch, logger):
        self.runtime = trt.Runtime(logger)
        self.engine = self.runtime.deserialize_cuda_engine(path.read_bytes())
        if self.engine is None:
            raise ValueError('Local engine rejected')
        self.context = self.engine.create_execution_context()
        if self.context is None or not self.context.set_input_shape('pixel_values', (1, 3, *shape)):
            raise ValueError('Input shape rejected')
        if tuple(self.context.get_tensor_shape('predicted_depth')) != (1, *shape):
            raise ValueError('Output shape mismatch')
        if any(self.engine.get_tensor_dtype(name) != trt.float32
               for name in ('pixel_values', 'predicted_depth')):
            raise ValueError('Unexpected I/O dtype')
        self.stream = torch.cuda.Stream()
        with torch.cuda.stream(self.stream):
            self.input = torch.empty((1, 3, *shape), device='cuda', dtype=torch.float32)
            self.output = torch.empty((1, *shape), device='cuda', dtype=torch.float32)
        for name, tensor in (('pixel_values', self.input), ('predicted_depth', self.output)):
            if not self.context.set_tensor_address(name, tensor.data_ptr()):
                raise ValueError('Tensor binding failed')
        self.start = torch.cuda.Event(enable_timing=True)
        self.end = torch.cuda.Event(enable_timing=True)

    def infer(self, tensor):
        with self.torch.cuda.stream(self.stream):
            self.input.copy_(self.torch.from_numpy(tensor))
            self.start.record(self.stream)
            if not self.context.execute_async_v3(self.stream.cuda_stream):
                raise RuntimeError('Inference failed')
            self.end.record(self.stream)
            self.stream.synchronize()
            elapsed = self.start.elapsed_time(self.end)
            output = self.output.cpu().numpy().copy()
        if not np.isfinite(output).all():
            raise ValueError('Nonfinite depth')
        return output, elapsed

    def close(self):
        if self.stream is not None:
            self.stream.synchronize()
        self.context = self.engine = self.runtime = None
        self.input = self.output = self.start = self.end = self.stream = None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--model-precision', choices=('fp16', 'fp32'), default='fp16',
                        help='ONNX used for the supplied locally built engines; not a runtime cast')
    args = parser.parse_args()
    directory = args.directory.resolve(strict=True)
    if (directory / 'report.json').exists() or (directory / 'review').exists():
        raise ValueError('Fresh result directory required')
    # Use only the locally built paired engines, derived from the pinned ONNX.
    manifest = json.loads((ROOT / 'models/da2-small/model-manifest.json').read_text())
    reference_manifest = json.loads((ROOT / 'models/da2-small/fp32-reference-manifest.json').read_text())
    for filename, expected in [('model_fp16.onnx', manifest['onnx_sha256']),
                               ('model_fp32.onnx', reference_manifest['sha256'])]:
        if digest(ROOT / 'out/models/da2-small' / filename) != expected:
            raise ValueError('Pinned ONNX integrity mismatch')
    report = dict(status='incomplete', shapes=SHAPES, engine_hashes={}, sources={}, cases=[],
                  model_precision=args.model_precision,
                  onnx_sha256=(manifest['onnx_sha256'] if args.model_precision == 'fp16'
                               else reference_manifest['sha256']),
                  scope='Depth-only paired shape experiment; host I/O included in wall. '
                  'No SBS, FG, scanout, headset or sustained throughput measurement.',
                  oracle_thresholds=dict(mae=.01, rmse=.015, maximum=.05,
                                         relative=.01, minimum_correlation=.999),
                  visual_review='pending', product_selection='not_promoted')
    (directory / 'review').mkdir()
    import torch
    import onnxruntime as ort
    from public_test_media import SOURCES
    torch.set_num_threads(1)
    options = ort.SessionOptions()
    options.intra_op_num_threads = 4
    reference = ort.InferenceSession(str(ROOT / 'out/models/da2-small/model_fp32.onnx'),
                                    sess_options=options, providers=['CPUExecutionProvider'])
    same_graph = ort.InferenceSession(str(ROOT / f'out/models/da2-small/model_{args.model_precision}.onnx'),
                                     sess_options=options, providers=['CPUExecutionProvider'])
    report['environment'] = dict(torch=torch.__version__, gpu=torch.cuda.get_device_name(),
                                  onnxruntime=ort.__version__, torch_cpu_threads=1)
    with os.add_dll_directory('C:/TensorRT/TensorRT-11.2.1.2/bin'):
        import tensorrt as trt
        logger = trt.Logger(trt.Logger.WARNING)
        report['environment']['tensorrt'] = trt.__version__
        engines = []
        try:
            for shape in SHAPES:
                path = directory / f'small-{shape[0]}x{shape[1]}.plan'
                report['engine_hashes'][path.name] = digest(path)
                engines.append(Engine(path, shape, trt, torch, logger))
            for source, expected in SOURCES.items():
                path = ROOT / 'out/public-video-source/uvg-vcm' / f'{source}.mp4'
                if digest(path) != expected:
                    raise ValueError('Public source integrity mismatch')
                report['sources'][source] = expected
                capture = cv2.VideoCapture(str(path))
                try:
                    for index in range(6):
                        ok, bgr = capture.read()
                        if not ok or bgr.shape != (2160, 3840, 3):
                            raise ValueError('Expected native 3840x2160 source')
                        frame = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                        outputs = {}
                        # Alternate order to limit systematic warmup/order bias.
                        for slot in ((0, 1) if index % 2 == 0 else (1, 0)):
                            shape, engine = SHAPES[slot], engines[slot]
                            label = f'{shape[0]}x{shape[1]}'
                            tensor = preprocess(frame, shape)
                            if index == 0:
                                for _ in range(10):
                                    engine.infer(tensor)
                            wall, gpu, prep = [], [], []
                            for _ in range(5):
                                started = time.perf_counter_ns()
                                tensor = preprocess(frame, shape)
                                prepared = time.perf_counter_ns()
                                depth, gpu_ms = engine.infer(tensor)
                                wall.append((time.perf_counter_ns()-started)/1e6)
                                prep.append((prepared-started)/1e6)
                                gpu.append(gpu_ms)
                            row = dict(source=source, frame=index, shape=label,
                                       wall_ms=wall, gpu_ms=gpu, preprocess_ms=prep)
                            if index == 0:
                                oracle = reference.run(['predicted_depth'], {'pixel_values': tensor})[0]
                                row['oracle'] = comparison(oracle, depth)
                                graph_oracle = same_graph.run(['predicted_depth'], {'pixel_values': tensor})[0]
                                row['same_graph_oracle'] = comparison(graph_oracle, depth)
                            report['cases'].append(row)
                            outputs[label] = depth[0]
                            print(source, index, label, round(statistics.median(wall), 3),
                                  row.get('oracle', {}).get('passed'), flush=True)
                        if index in (0, 5):
                            # One common scale per paired preview, no independent contrast fitting.
                            low = min(float(np.quantile(d, .02)) for d in outputs.values())
                            high = max(float(np.quantile(d, .98)) for d in outputs.values())
                            tiles = [cv2.resize(bgr, (960, 540))]
                            for label in ('518x518', '392x700'):
                                gray = np.uint8(np.clip((outputs[label]-low)/max(high-low, 1e-6), 0, 1)*255)
                                tile = cv2.resize(cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR), (960, 540))
                                cv2.putText(tile, label, (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                                tiles.append(tile)
                            if not cv2.imwrite(str(directory/'review'/f'{source}-{index}.png'), np.hstack(tiles)):
                                raise RuntimeError('Review write failed')
                finally:
                    capture.release()
        finally:
            errors = []
            for engine in reversed(engines):
                try:
                    engine.close()
                except Exception as error:
                    errors.append(error)
            if errors:
                raise RuntimeError('Engine cleanup failed') from errors[0]
    report['status'] = 'measured'
    report['oracle_passed'] = all(row['oracle']['passed'] for row in report['cases'] if 'oracle' in row)
    report['same_graph_oracle_passed'] = all(row['same_graph_oracle']['passed']
        for row in report['cases'] if 'same_graph_oracle' in row)
    report['source_hash'] = digest(__file__)
    (directory/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('MEASURED', directory/'report.json', flush=True)


if __name__ == '__main__':
    main()
