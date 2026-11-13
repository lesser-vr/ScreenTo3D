"""Generated planes through actual host, shared-texture and VFG projection DLLs.

No capture or private media. The legacy DLL is a pinned negative control, not a
fallback. Physical stereo sign is checked independently of pixel parity.
"""
import argparse
import ctypes as ct
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path

import numpy as np
import torch

from screento3d_app.desktop_jobs import ROOT
from screento3d_app.live_gpu_candidate import DLL_PATH, DLL_SHA256
from screento3d_app.live_texture_pool import LiveTexturePool
from tests.test_stereo_geometry import geometry_fixture, measure_planes


OLD = ROOT / "out/live-depth-parallel/live_depth.dll"
OLD_HASH = "e88697254fa9d81ade5d19b84b2f9107d5d1211fbeb9243cb4ec0af77b7ae6df"


class LegacyPool(LiveTexturePool):
    library_path = ROOT / "out/live-texture-runtime/live_texture_runtime.dll"
    library_sha256 = "8bf16e363dd1fc6002be598335029925113b2afa2b9bdd00f12519a8002a9eae"


def load(path, digest):
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, path
    dll = ct.CDLL(str(path))
    dll.live_create.argtypes = [ct.c_void_p, ct.c_int, ct.c_int, ct.c_void_p]
    dll.live_destroy.argtypes = [ct.c_void_p]
    dll.live_post_source.argtypes = [ct.c_void_p] * 3 + [ct.c_int] * 2 + [
        ct.c_double, ct.c_float, ct.c_float, ct.c_int, ct.c_void_p, ct.c_double]
    dll.live_project.argtypes = [ct.c_void_p] * 2 + [ct.c_float] * 2 + [ct.c_int] + [ct.c_void_p] * 3
    return dll


def check_cuda(result):
    if result != 0:
        raise RuntimeError(f"CUDA status {result}")


def context(stack, dll, frame, depth, stream):
    height, width = frame.shape[:2]
    handle = ct.c_void_p()
    check_cuda(dll.live_create(ct.byref(handle), width, height, stream.cuda_stream))
    stack.callback(lambda: check_cuda(dll.live_destroy(handle)))
    check_cuda(dll.live_post_source(handle, frame.ctypes.data, depth.ctypes.data,
                                    0, 1, .35, .04, .08, 1, None, .008))
    stream.synchronize()
    return handle


def host(dll, handle, frame, scale):
    left, right = np.empty_like(frame), np.empty_like(frame)
    invalid = ct.c_int()
    check_cuda(dll.live_project(handle, None, .5, scale, 1,
                               left.ctypes.data, right.ctypes.data, ct.byref(invalid)))
    assert not invalid.value
    return np.concatenate((left, right), axis=1)


def texture(pool, handle, scale):
    result = np.empty((pool.height, pool.width, 4), np.uint8)
    pool.check(pool.dll.live_pool_publish(pool.handle, handle, .5, scale, 1, None, 0, 0))
    pool.check(pool.dll.live_pool_readback(pool.handle, 0, result.ctypes.data))
    assert np.all(result[:, :, 3] == 255)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from native_path import BRIDGE, BRIDGE_HASH, BridgePool
    current, legacy = load(DLL_PATH, DLL_SHA256), load(OLD, OLD_HASH)
    bridge = load(BRIDGE, BRIDGE_HASH)
    bridge.vfg_project.argtypes = [ct.c_void_p] * 2 + [ct.c_float] * 2 + [ct.c_int, ct.c_void_p]
    bridge.vfg_publish.argtypes = [ct.c_void_p] * 2 + [ct.c_int] * 3 + [ct.c_void_p]
    rows = []
    stream = torch.cuda.Stream()
    for width, height in ((256, 72), (1920, 1080), (3840, 2160)):
        frame, depth = geometry_fixture(width, height)
        with ExitStack() as stack:
            old_handle = context(stack, legacy, frame, depth, stream)
            handle = context(stack, current, frame, depth, stream)
            old_pool = stack.enter_context(LegacyPool(width, height, diagnostic=True))
            pool = stack.enter_context(LiveTexturePool(width, height, diagnostic=True))
            vfg_pool = stack.enter_context(BridgePool(width, height, diagnostic=True))
            with torch.cuda.stream(stream):
                pixels = torch.empty((height, width * 2, 4), dtype=torch.uint8, device="cuda")
            for strength in (1., .5):
                scale = width * .026 * strength
                before, after = host(legacy, old_handle, frame, scale), host(current, handle, frame, scale)
                assert np.array_equal(after, np.concatenate((before[:, width:], before[:, :width]), axis=1))
                assert np.array_equal(texture(old_pool, old_handle, scale)[:, :, :3], before)
                native = texture(pool, handle, scale)
                assert np.array_equal(native[:, :, :3], after)
                vfg_pool.check(bridge.vfg_project(handle, pixels.data_ptr(), .5, scale, 1, None))
                with torch.cuda.stream(stream):
                    projected = pixels.cpu().numpy()
                assert np.array_equal(projected, native)
                vfg_pool.check(bridge.vfg_publish(vfg_pool.handle, pixels.data_ptr(),
                                                 width * 2, height, 0, stream.cuda_stream))
                delivered = np.empty_like(native)
                vfg_pool.check(vfg_pool.dll.live_pool_readback(vfg_pool.handle, 0, delivered.ctypes.data))
                assert np.array_equal(delivered, native)
                old_sign, new_sign = measure_planes(before), measure_planes(delivered)
                assert old_sign["near"] < 0 < old_sign["far"]
                assert new_sign["far"] < 0 < new_sign["near"] and new_sign["screen"] == 0
                row = dict(size=[width, height], strength=strength, legacy_left_minus_right=old_sign,
                           corrected_left_minus_right=new_sign, exact_eye_swap=True,
                           host_native_vfg_exact=True)
                rows.append(row)
                print(json.dumps(row), flush=True)
            stream.synchronize()
            del pixels
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dict(passed=True, rows=rows, dll=DLL_SHA256,
        texture=LiveTexturePool.library_sha256, vfg=BRIDGE_HASH,
        scope="Synthetic projection/publication geometry; no inference, VFG interpolation or physical viewing"), indent=2))


if __name__ == "__main__":
    main()
