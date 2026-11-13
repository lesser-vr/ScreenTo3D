"""Independent geometry/mask oracle, public depth pairs and bounded cost checks."""

import argparse
from contextlib import ExitStack
import ctypes as ct
import json
import os
from pathlib import Path

import cv2
import numpy as np
import torch

from check_stereo_geometry_gpu import load, context, check_cuda
from check_stereo_stability_gpu import project
from check_depth_range import configure, allocate, post
from screento3d_app.live_gpu_candidate import DLL_PATH, DLL_SHA256
from screento3d_app.live_policy import resolve_live
from screento3d_app.desktop_jobs import ROOT, BUNDLE
from screento3d_app.live_scene_history import LiveSceneHistory
from screento3d_app.motion_history import MotionHistory
from public_test_media import PublicFrames, SOURCES, ATTRIBUTION

OLD = ROOT / "out/live-depth-range/live_depth.dll"
OLD_HASH = "8fae90940f546b7a779de54b8792b7476e309598a0c7b26e5abb50bee2f11bfa"


def setup(dll):
    configure(dll)
    dll.live_set_window.argtypes = [ct.c_void_p, ct.c_double, ct.c_int]
    dll.live_window_snapshot.argtypes = [ct.c_void_p, ct.c_void_p]
    for name in ("live_set_subpixel", "live_set_coverage", "live_set_parallel"):
        getattr(dll, name).argtypes = [ct.c_void_p, ct.c_int]
    return dll


def settings(dll, handle):
    for name in ("live_set_subpixel", "live_set_coverage", "live_set_parallel"):
        check_cuda(getattr(dll, name)(handle, 1))


def state(dll, handle):
    result = np.empty(4, np.float32)
    check_cuda(dll.live_window_snapshot(handle, result.ctypes.data))
    return result


def target(depth, convergence, scale):
    height, width = depth.shape
    shift = (depth - np.float32(convergence)) * np.float32(scale) * np.float32(0.5)
    x = np.arange(width)[None, :]
    disparity = np.minimum(shift * 2, np.float32(width) * np.float32(0.015))
    return np.array(
        [
            np.max(np.where((shift > 0) & (distance < shift), disparity, 0))
            for distance in (x, width - 1 - x)
        ],
        np.float32,
    )


def check_mask(before, after, widths):
    width = before.shape[1] // 2
    expected = before.copy()
    for eye, amount in enumerate(widths):
        distance = np.arange(width, dtype=np.float32)
        if eye:
            distance = distance[::-1]
        weight = np.clip(distance + 1 - amount, 0, 1)
        expected[:, eye * width : (eye + 1) * width] = np.floor(
            before[:, eye * width : (eye + 1) * width].astype(np.float32)
            * weight[None, :, None]
            + 0.5
        ).astype(np.uint8)
    assert np.array_equal(after, expected), (
        "Output changed outside the declared straight edge masks"
    )
    return float(np.any(before != after, axis=2).mean())


def synthetic(dll):
    old = load(OLD, OLD_HASH)
    for name in ("live_set_subpixel", "live_set_coverage", "live_set_parallel"):
        getattr(old, name).argtypes = [ct.c_void_p, ct.c_int]
    stream = torch.cuda.Stream()
    rows = []
    for width, height in (
        (64, 32),
        (1920, 1080),
        (3440, 1440),
        (1080, 1920),
        (3840, 2160),
    ):
        rgb = np.random.default_rng(38).integers(20, 240, (height, width, 3), np.uint8)
        depth = np.full((height, width), 0.45, np.float32)
        with ExitStack() as stack:
            handle = context(stack, dll, rgb, depth, stream)
            settings(dll, handle)
            prior = context(stack, old, rgb, depth, stream)
            settings(old, prior)
            for strength in (0.25, 0.5, 2.0):
                scale = width * 0.026 * strength
                for pattern in (
                    "screen",
                    "far",
                    "near",
                    "left",
                    "right",
                    "center",
                    "thin",
                ):
                    depth[:] = 0.2
                    if pattern == "screen":
                        depth[:] = 0.45
                    if pattern == "near":
                        depth[:] = 0.95
                    if pattern in ("left", "thin"):
                        depth[
                            height // 4 : height * 3 // 4,
                            : 1 if pattern == "thin" else width // 4,
                        ] = 0.95
                    if pattern == "right":
                        depth[height // 4 : height * 3 // 4, width * 3 // 4 :] = 0.95
                    if pattern == "center":
                        depth[
                            height // 4 : height * 3 // 4, width // 3 : width * 2 // 3
                        ] = 0.95
                    check_cuda(dll.live_set_window(handle, -1, 1))
                    before = project(dll, handle, rgb, depth, 0.45, scale)
                    reference = project(old, prior, rgb, depth, 0.45, scale)
                    assert np.array_equal(before, reference), (
                        "Disabled path differs from prior binary"
                    )
                    check_cuda(dll.live_set_window(handle, 1 / 60, 1))
                    after = project(dll, handle, rgb, depth, 0.45, scale)
                    values = state(dll, handle)
                    expected = target(depth, 0.45, scale)
                    assert np.allclose(values[:2], expected, rtol=0, atol=2e-5), (
                        values,
                        expected,
                    )
                    assert np.array_equal(values[:2], values[2:])
                    assert np.all(values[2:] <= width * 0.015 + 2e-5)
                    fraction = check_mask(before, after, values[2:])
                    if pattern in ("screen", "far", "center"):
                        assert np.array_equal(after, before)
                    rows.append(
                        dict(
                            size=[width, height],
                            strength=strength,
                            pattern=pattern,
                            widths=values[2:].tolist(),
                            changed_fraction=fraction,
                        )
                    )
    # Source-time release, immediate expansion and cut reset, independent of rate.
    rgb = np.full((32, 512, 3), 200, np.uint8)
    depth = np.full((32, 512), 0.95, np.float32)
    release = []
    with ExitStack() as stack:
        for hz in (30, 60, 120):
            handle = context(stack, dll, rgb, depth, stream)
            check_cuda(dll.live_set_window(handle, 1 / hz, 1))
            project(dll, handle, rgb, depth, 0.45, 13.312)
            initial = state(dll, handle)[2:].copy()
            for _ in range(hz // 2):
                check_cuda(dll.live_set_window(handle, 1 / hz, 0))
                project(dll, handle, rgb, np.full_like(depth, 0.2), 0.45, 13.312)
            end = state(dll, handle)[2:]
            assert np.allclose(end, initial * np.exp(-0.5 / 0.2), atol=2e-5)
            release.append(end.tolist())
            check_cuda(dll.live_set_window(handle, 1 / hz, 0))
            project(dll, handle, rgb, depth, 0.45, 13.312)
            assert np.array_equal(state(dll, handle)[2:], initial)
            check_cuda(dll.live_set_window(handle, 1 / hz, 1))
            project(dll, handle, rgb, np.full_like(depth, 0.2), 0.45, 13.312)
            assert not state(dll, handle).any()
            for dt in (0, 0.100001, float("nan")):
                assert dll.live_set_window(handle, dt, 0) != 0
    return dict(
        cases=rows,
        half_second_release=release,
        disabled_exact=True,
        geometry_exact=True,
        mask_oracle_exact=True,
        reset_exact=True,
    )


def public(dll, model):
    policy = resolve_live(
        "balanced" if model == "base" else "performance", strength=0.5
    )
    results = []
    with ExitStack() as stack:
        runtime = Path("C:/TensorRT/TensorRT-11.2.1.2/bin")
        stack.enter_context(os.add_dll_directory(str(runtime)))
        if model == "base":
            from screento3d_app.da2_base import binding

            backend = binding(ROOT / "out/da2-base-local", runtime)
            backend.input_validator(dict(width=1920, height=1080))
            engine = stack.enter_context(backend.engine_factory(None))
            stream = engine.stream
        else:
            from screento3d_app.resources import configure_resource_root
            from screento3d_app.small_gpu_input import SmallGpuCaptureEngine
            from screento3d_app.pipeline import preprocess

            configure_resource_root(BUNDLE)
            engine = stack.enter_context(SmallGpuCaptureEngine())
            stream = engine.torch_stream
        for name in SOURCES:
            with ExitStack() as scene:
                handle = allocate(scene, dll, 1920, 1080, stream.cuda_stream)
                settings(dll, handle)
                motion = scene.enter_context(
                    MotionHistory(
                        1920, 1080, stream.cuda_stream, DLL_SHA256, diagnostic=True
                    )
                )
                history = LiveSceneHistory(policy.scene_cut_threshold)
                rows = []
                for index, rgb in enumerate(PublicFrames(name, 90)):
                    if index % 3:
                        continue
                    raw = (
                        np.ascontiguousarray(engine.infer(rgb)[0])
                        if model == "base"
                        else cv2.resize(
                            engine.infer(preprocess(rgb)).squeeze(),
                            (1920, 1080),
                            interpolation=cv2.INTER_CUBIC,
                        )
                    )
                    event = history.inspect(rgb)
                    reset = index == 0 or index == 45 or event.cut
                    post(dll, handle, rgb, raw, policy, reset, 1 / 20)
                    motion.apply(
                        handle, 1_000_000_000 + index * 16_666_667, reset=reset
                    )
                    depth = motion.snapshot(handle)[0]
                    check_cuda(dll.live_set_window(handle, -1, 0))
                    before = project(
                        dll,
                        handle,
                        rgb,
                        depth,
                        policy.convergence,
                        1920 * policy.divergence,
                    )
                    check_cuda(dll.live_set_window(handle, 1 / 20, int(reset)))
                    after = project(
                        dll,
                        handle,
                        rgb,
                        depth,
                        policy.convergence,
                        1920 * policy.divergence,
                    )
                    values = state(dll, handle)
                    assert np.allclose(
                        values[:2],
                        target(depth, policy.convergence, 1920 * policy.divergence),
                        atol=2e-5,
                    )
                    assert np.all(values[2:] + 1e-5 >= values[:2])
                    fraction = check_mask(before, after, values[2:])
                    rows.append(
                        dict(
                            frame=index,
                            reset=bool(reset),
                            widths=values[2:].tolist(),
                            changed_fraction=fraction,
                        )
                    )
                    history.commit(event)
                summary = dict(
                    model=model,
                    clip=name,
                    frames=len(rows),
                    max_width_px=np.max([r["widths"] for r in rows], axis=0).tolist(),
                    mean_changed_fraction=float(
                        np.mean([r["changed_fraction"] for r in rows])
                    ),
                )
                print(json.dumps(summary), flush=True)
                results.append(dict(summary=summary, rows=rows))
    return results


def benchmark(dll):
    from screento3d_app.live_texture_pool import LiveTexturePool

    stream = torch.cuda.Stream()
    rows = []
    for width, height in ((1920, 1080), (3840, 2160)):
        rgb = cv2.resize(PublicFrames("FloorballGame", 1)[0], (width, height))
        depth = np.full((height, width), 0.95, np.float32)
        with ExitStack() as stack:
            handle = context(stack, dll, rgb, depth, stream)
            settings(dll, handle)
            # Store analytic source depth once; publication below uses the same depth.
            project(dll, handle, rgb, depth, 0.45, width * 0.013)
            pool = stack.enter_context(LiveTexturePool(width, height, diagnostic=True))
            readback = np.empty((height, width * 2, 4), np.uint8)
            times = {0: [], 1: []}
            for iteration in range(24):
                for enabled in (0, 1) if iteration % 2 else (1, 0):
                    check_cuda(
                        dll.live_set_window(
                            handle, 1 / 60 if enabled else -1, int(iteration == 0)
                        )
                    )
                    start, end = (
                        torch.cuda.Event(enable_timing=True),
                        torch.cuda.Event(enable_timing=True),
                    )
                    start.record(stream)
                    pool.check(
                        pool.dll.live_pool_publish(
                            pool.handle, handle, 0.45, width * 0.013, 1, None, 0, 0
                        )
                    )
                    end.record(stream)
                    end.synchronize()
                    if iteration >= 4:
                        times[enabled].append(start.elapsed_time(end))
                    pool.check(
                        pool.dll.live_pool_readback(
                            pool.handle, 0, readback.ctypes.data
                        )
                    )
            values = [float(np.median(times[key])) for key in (0, 1)]
            rows.append(
                dict(
                    size=[width, height],
                    native_projection_ms=values,
                    added_ms=values[1] - values[0],
                )
            )
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", choices=("base", "small"))
    parser.add_argument("--benchmark", action="store_true")
    args = parser.parse_args()
    cv2.setNumThreads(1)
    torch.set_num_threads(4)
    dll = setup(load(DLL_PATH, DLL_SHA256))
    report = dict(passed=False, dll=DLL_SHA256)
    if args.benchmark:
        report["benchmark"] = benchmark(dll)
        print(json.dumps(report["benchmark"]))
    elif args.model:
        report.update(public=public(dll, args.model), attribution=ATTRIBUTION)
    else:
        report["synthetic"] = synthetic(dll)
    report["passed"] = True
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2))
    print("Passed", flush=True)


if __name__ == "__main__":
    main()
