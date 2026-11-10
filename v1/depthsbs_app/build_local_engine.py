"""Isolated builder for the verified Base and VDA ONNX distribution graphs."""
from .messages import ErrorMessage as E

from .messages import encode_message
import hashlib
import sys
from pathlib import Path

import numpy as np

from .desktop_jobs import BUNDLE
from .engine_cache import TRT_VERSION, device_identity, save_record
from .resources import configure_resource_root, prepare_dll_search_path


def sample_outputs(folder, key, width):
    """Exercise the input/output contract, including a real VDA cache transition."""
    import torch
    import tensorrt as trt
    from .vda_artifacts import cache_layout
    runtime = trt.Runtime(trt.Logger(trt.Logger.ERROR))
    samples, previous = {}, {}
    rng = np.random.default_rng(9071)
    base = key == 'da2-base'
    for stage in (('model',) if base else ('warmup', 'cached')):
        engine = runtime.deserialize_cuda_engine((folder/f'{stage}.plan').read_bytes())
        if engine is None:
            raise RuntimeError(E('E_ENGINE_OPEN_FAILED', v0=stage))
        ctx = engine.create_execution_context()
        image_shape = (1, 3, 518, width) if base else (1, 1, 3, 518, width)
        inputs = {'image': torch.from_numpy(rng.uniform(-1, 1, image_shape).astype('float32')).cuda()}
        expected = {'depth': (1, 518, width) if base else (1, 1, 518, width)}
        if not base:
            for i, (spatial, channels) in enumerate(cache_layout((518, width))):
                expected[f'new_cache_{i}'] = (spatial, 1, channels)
                if stage == 'cached':
                    inputs[f'cache_{i}'] = previous[f'new_cache_{i}'].expand(-1, 31, -1).contiguous()
        if set(inputs) | set(expected) != {engine.get_tensor_name(i) for i in range(engine.num_io_tensors)}:
            raise ValueError('Engine tensor names differ from the expected model')
        outputs = {name: torch.empty(shape, device='cuda') for name, shape in expected.items()}
        for name, tensor in (inputs | outputs).items():
            mode = trt.TensorIOMode.INPUT if name in inputs else trt.TensorIOMode.OUTPUT
            if (engine.get_tensor_dtype(name) != trt.float32 or engine.get_tensor_mode(name) != mode
                    or tuple(engine.get_tensor_shape(name)) != tuple(tensor.shape)
                    or not ctx.set_tensor_address(name, tensor.data_ptr())):
                raise ValueError(f'Invalid engine tensor: {name}')
        if not ctx.execute_async_v3(torch.cuda.current_stream().cuda_stream):
            raise RuntimeError(E('E_ENGINE_TEST_FAILED'))
        torch.cuda.synchronize()
        for name, tensor in outputs.items():
            if not bool(tensor.isfinite().all()):
                raise ValueError(f'Nonfinite output: {name}')
            samples[f'{stage}_{name}'] = tensor.flatten()[::max(1, tensor.numel()//256)].cpu().numpy()
        previous = outputs
        del ctx, engine
    return samples


def compile_graph(graph_bytes, destination, trt, logger):
    builder = trt.Builder(logger)
    network = builder.create_network(0)
    parser = trt.OnnxParser(network, logger)
    if not parser.parse(graph_bytes):
        raise ValueError(str([str(parser.get_error(i)) for i in range(parser.num_errors)]))
    config = builder.create_builder_config()
    config.clear_flag(trt.BuilderFlag.TF32)
    config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, 2 * 1024**3)
    plan = builder.build_serialized_network(network, config)
    if plan is None:
        raise RuntimeError(E('E_ENGINE_BUILD_FAILED'))
    data = bytes(plan)
    destination.write_bytes(data)
    return dict(file=destination.name, sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))


def build(key, folder):
    from .optional_models import PACKS, GRAPH_HASHES, installed_path
    folder = folder.resolve(strict=True)
    if (key not in GRAPH_HASHES or folder.name != 'ready' or not folder.parent.name.startswith('.install-')
            or folder.parent.parent != installed_path(key).resolve().parent):
        raise ValueError('Invalid model installation staging directory')
    configure_resource_root(BUNDLE)
    runtime_directory = prepare_dll_search_path()
    import tensorrt as trt
    if trt.__version__ != TRT_VERSION:
        raise ValueError(E('E_ENGINE_VERSION_MISMATCH'))
    device = device_identity()
    logger = trt.Logger(trt.Logger.ERROR)
    profiles = {}
    for width in (896, 924):
        base = key == 'da2-base'
        name = f'518x{width}-fp16'
        profile = folder/name
        engines = {}
        for stage in (('model',) if base else ('warmup', 'cached')):
            graph = profile/f'{stage}.onnx'
            graph_bytes = graph.read_bytes()
            if hashlib.sha256(graph_bytes).hexdigest() != GRAPH_HASHES[key][width][stage]:
                raise ValueError(E('E_MODEL_GRAPH_INVALID'))
            engines[stage] = compile_graph(graph_bytes, profile/f'{stage}.plan', trt, logger)
            del graph_bytes
            graph.unlink()
        samples = sample_outputs(profile, key, width)
        reference = profile/'reference.npz'
        with np.load(reference, allow_pickle=False) as stored:
            if set(stored.files) != set(samples):
                raise ValueError('Invalid reference tensor set')
            for label, actual in samples.items():
                tolerance = 0.02 if base else 0.001
                np.testing.assert_allclose(actual, stored[label], atol=tolerance, rtol=tolerance)
        reference.unlink()
        profiles[name] = dict(engines=engines, precision='mixed-fp16', gpu=device['gpu'], compute_capability=device['compute_capability'],
                              tensorrt=trt.__version__, input_shape=[1, 3, 518, width] if base else [1, 1, 3, 518, width],
                              validation='local-depth-and-cache-samples' if not base else 'local-depth-samples')
    save_record(folder/'build.receipt', dict(source=PACKS[key].sha, device=device, profiles=profiles))


if __name__ == '__main__':
    try:
        build(sys.argv[1], Path(sys.argv[2]))
    except Exception as exc:
        from .messages import as_error
        Path(sys.argv[3]).write_bytes(encode_message(as_error(exc), limit=2000))
        raise
