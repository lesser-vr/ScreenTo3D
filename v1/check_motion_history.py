"""Real NVOF history against the range-only baseline; public/analytic inputs only."""

import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path

import cv2
import numpy as np
import torch

from check_depth_range import configure, allocate, post
from check_stereo_geometry_gpu import load
from depthsbs_app.live_gpu_candidate import DLL_PATH, DLL_SHA256
from depthsbs_app.motion_history import MotionHistory, DLL_SHA256 as MOTION_HASH
from depthsbs_app.live_policy import resolve_live
from depthsbs_app.live_scene_history import LiveSceneHistory
from depthsbs_app.desktop_jobs import ROOT, BUNDLE
from public_test_media import PublicFrames, SOURCES, ATTRIBUTION


def synthetic(dll, policy):
    rng = np.random.default_rng(17)
    image = rng.integers(0, 256, (256, 512, 3), dtype=np.uint8)
    image = cv2.GaussianBlur(image, (5, 5), 0)
    yy, xx = np.indices((256, 512))
    base = (0.25 + 0.4 * xx / 511).astype(np.float32)
    # Normalization is fixed by a broad ramp; jitter is confined to the interior.
    rows = []
    stream = torch.cuda.Stream()
    with ExitStack() as stack:
        handle = allocate(stack, dll, 512, 256, stream.cuda_stream)
        motion = stack.enter_context(
            MotionHistory(512, 256, stream.cuda_stream, DLL_SHA256, diagnostic=True)
        )
        prev = None
        for index in range(12):
            shift = index * 3
            rgb = np.roll(image, shift, axis=1).copy()
            raw = np.roll(base, shift, axis=1).copy()
            raw[50:200, 80 + shift : 400 + shift] += 0.006 if index % 2 else -0.006
            reset = index in (0, 6)
            baseline, _, _ = post(dll, handle, rgb, raw, policy, reset, 1 / 30)
            motion.apply(handle, 1_000_000_000 + index * 33_333_333, reset=reset)
            actual, history, accepted = motion.snapshot(handle)
            assert np.array_equal(history, baseline), (
                "Filtered result fed back into history"
            )
            assert np.array_equal(actual[accepted == 0], baseline[accepted == 0]), (
                "Rejected history changed depth"
            )
            assert (
                np.isfinite(actual).all()
                and np.abs(actual - baseline).max() <= 0.012001
            )
            if reset:
                assert np.array_equal(actual, baseline) and not accepted.any()
            if prev is not None and not reset:
                region = (slice(70, 180), slice(100 + shift, 350 + shift))
                old_base, old_actual = prev
                errors = [
                    float(np.abs(a - np.roll(b, 3, axis=1))[region].mean())
                    for a, b in ((baseline, old_base), (actual, old_actual))
                ]
                rows.append(
                    dict(errors=errors, accepted=float(accepted[region].mean()))
                )
            prev = baseline, actual
        scores = np.mean([r["errors"] for r in rows], axis=0)
        acceptance = float(np.mean([r["accepted"] for r in rows]))
        assert acceptance > 0.05, (acceptance, scores)
        assert scores[1] < scores[0], scores
        # A newly visible region with no photometric match must use current depth.
        rgb = np.roll(image, 36, axis=1).copy()
        rgb[90:170, 200:300] = 255
        raw = np.roll(base, 36, axis=1).copy()
        raw[90:170, 200:300] = 0.5
        baseline, _, _ = post(dll, handle, rgb, raw, policy, False, 1 / 30)
        motion.apply(handle, 1_400_000_000)
        actual, _, accepted = motion.snapshot(handle)
        assert not accepted[92:168, 202:298].any(), (
            "Newly visible region accepted stale history"
        )
        assert np.array_equal(actual[92:168, 202:298], baseline[92:168, 202:298])
        # Time discontinuities and explicit invalidation cannot carry history.
        for timestamp, invalidate in (
            (1_600_000_000, False),
            (1_500_000_000, False),
            (1_533_333_333, True),
        ):
            if invalidate:
                motion.invalidate()
            baseline, _, _ = post(dll, handle, rgb, raw, policy, False, 1 / 30)
            motion.apply(handle, timestamp)
            actual, _, accepted = motion.snapshot(handle)
            assert np.array_equal(actual, baseline) and not accepted.any()
        # A real depth jump must not be averaged away even with matching motion.
        for index in range(2):
            shift = index * 3
            rgb = np.roll(image, shift, axis=1).copy()
            raw = np.roll(base, shift, axis=1).copy()
            raw[50:200, 80 + shift : 400 + shift] += 0.012 if index else -0.012
            baseline, _, _ = post(dll, handle, rgb, raw, policy, index == 0, 1 / 30)
            motion.apply(handle, 2_000_000_000 + index * 33_333_333, reset=index == 0)
        actual, _, accepted = motion.snapshot(handle)
        region = (slice(70, 180), slice(103, 353))
        assert not accepted[region].any() and np.array_equal(
            actual[region], baseline[region]
        )
    return dict(
        temporal_mae=scores.tolist(),
        accepted=acceptance,
        reset_exact=True,
        rejected_exact=True,
        nonrecursive=True,
        newly_visible_exact=True,
        time_discontinuity_exact=True,
        depth_jump_exact=True,
    )


def benchmark(dll, policy):
    image = PublicFrames("FloorballGame", 1)[0]
    stream = torch.cuda.Stream()
    rows = []
    for width, height in ((16, 16), (4096, 16), (16, 2160), (1920, 1080), (3840, 2160)):
        with ExitStack() as stack:
            handle = allocate(stack, dll, width, height, stream.cuda_stream)
            motion = stack.enter_context(
                MotionHistory(width, height, stream.cuda_stream, DLL_SHA256)
            )
            rgb = cv2.resize(image, (width, height))
            raw = np.tile(np.linspace(0.1, 0.9, width, dtype=np.float32), (height, 1))
            times = []
            for index in range(35):
                frame = np.roll(rgb, index * 3, axis=1).copy()
                post(dll, handle, frame, raw, policy, index == 0, 1 / 60)
                began, ended = (
                    torch.cuda.Event(enable_timing=True),
                    torch.cuda.Event(enable_timing=True),
                )
                began.record(stream)
                motion.apply(
                    handle, 1_000_000_000 + index * 16_666_667, reset=index == 0
                )
                ended.record(stream)
                ended.synchronize()
                if index >= 5:
                    times.append(began.elapsed_time(ended))
            result = np.empty_like(raw)
            motion.read_depth(handle, result)
            assert np.isfinite(result).all()
            rows.append(
                dict(
                    size=[width, height],
                    gpu_ms_p50=float(np.median(times)),
                    gpu_ms_p95=float(np.percentile(times, 95)),
                )
            )
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=("base", "small"), default="base")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--synthetic-only", action="store_true")
    parser.add_argument("--benchmark", action="store_true")
    args = parser.parse_args()
    cv2.setNumThreads(1)
    torch.set_num_threads(4)
    dll = configure(load(DLL_PATH, DLL_SHA256))
    policy = resolve_live(
        "balanced" if args.model == "base" else "performance", strength=0.5
    )
    report = dict(
        passed=False,
        model=args.model,
        motion_hash=MOTION_HASH,
        synthetic=synthetic(dll, policy),
        clips=[],
        attribution=ATTRIBUTION,
    )
    print(json.dumps(report["synthetic"]), flush=True)
    if args.benchmark:
        report["benchmark"] = benchmark(dll, policy)
        print(json.dumps(report["benchmark"]), flush=True)
    if not args.synthetic_only:
        with ExitStack() as stack:
            runtime = Path("C:/TensorRT/TensorRT-11.2.1.2/bin")
            stack.enter_context(os.add_dll_directory(str(runtime)))
            if args.model == "base":
                from depthsbs_app.da2_base import binding

                backend = binding(ROOT / "out/da2-base-local", runtime)
                backend.input_validator(dict(width=1920, height=1080))
                engine = stack.enter_context(backend.engine_factory(None))
                stream = engine.stream
            else:
                from depthsbs_app.resources import configure_resource_root
                from depthsbs_app.small_gpu_input import SmallGpuCaptureEngine
                from depthsbs_app.pipeline import preprocess

                configure_resource_root(BUNDLE)
                engine = stack.enter_context(SmallGpuCaptureEngine())
                stream = engine.torch_stream
            xx, yy = np.meshgrid(
                np.arange(480, dtype=np.float32), np.arange(270, dtype=np.float32)
            )
            for name in SOURCES:
                with ExitStack() as scene:
                    handle = allocate(scene, dll, 1920, 1080, stream.cuda_stream)
                    motion = scene.enter_context(
                        MotionHistory(
                            1920, 1080, stream.cuda_stream, DLL_SHA256, diagnostic=True
                        )
                    )
                    scene_history = LiveSceneHistory(policy.scene_cut_threshold)
                    scorer = cv2.DISOpticalFlow_create(
                        cv2.DISOPTICAL_FLOW_PRESET_MEDIUM
                    )
                    previous = prior_gray = None
                    rows = []
                    for index, rgb in enumerate(PublicFrames(name, 180)):
                        if index % 2:
                            continue
                        raw = (
                            np.ascontiguousarray(engine.infer(rgb)[0])
                            if args.model == "base"
                            else cv2.resize(
                                engine.infer(preprocess(rgb)).squeeze(),
                                (1920, 1080),
                                interpolation=cv2.INTER_CUBIC,
                            )
                        )
                        event = scene_history.inspect(rgb)
                        reset = previous is None or event.cut or index == 90
                        baseline, _, _ = post(
                            dll, handle, rgb, raw, policy, reset, 1 / 30
                        )
                        began, ended = (
                            torch.cuda.Event(enable_timing=True),
                            torch.cuda.Event(enable_timing=True),
                        )
                        began.record(stream)
                        motion.apply(
                            handle, 1_000_000_000 + index * 16_666_667, reset=reset
                        )
                        ended.record(stream)
                        ended.synchronize()
                        candidate, history, accepted = motion.snapshot(handle)
                        assert np.array_equal(history, baseline)
                        assert np.array_equal(
                            candidate[accepted == 0], baseline[accepted == 0]
                        )
                        if reset:
                            assert np.array_equal(candidate, baseline)
                        small = [
                            cv2.resize(d, (480, 270)) for d in (baseline, candidate)
                        ]
                        gray = cv2.resize(
                            cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), (480, 270)
                        )
                        row = dict(
                            frame=index,
                            reset=bool(reset),
                            accepted=float(accepted.mean()),
                            gpu_ms=began.elapsed_time(ended),
                            max_change=float(np.abs(candidate - baseline).max()),
                        )
                        if not reset:
                            flow = scorer.calc(gray, prior_gray, None)
                            mx, my = xx + flow[:, :, 0], yy + flow[:, :, 1]
                            old_gray = cv2.remap(prior_gray, mx, my, cv2.INTER_LINEAR)
                            mask = (
                                (mx > 1)
                                & (mx < 479)
                                & (my > 1)
                                & (my < 269)
                                & (np.abs(gray.astype(float) - old_gray) < 8)
                            )
                            edge = (
                                cv2.dilate(small[0], np.ones((3, 3), np.uint8))
                                - cv2.erode(small[0], np.ones((3, 3), np.uint8))
                            ) > 0.03
                            moving = np.linalg.norm(flow, axis=2) > 0.5
                            row["error_px"] = []
                            for k in range(2):
                                residual = (
                                    np.abs(
                                        small[k]
                                        - cv2.remap(
                                            previous[k], mx, my, cv2.INTER_LINEAR
                                        )
                                    )
                                    * 1920
                                    * policy.divergence
                                )
                                row["error_px"].append(
                                    {
                                        zone: float(residual[m].mean())
                                        if m.any()
                                        else None
                                        for zone, m in (
                                            ("mean", mask),
                                            ("edge", mask & edge),
                                            ("moving", mask & moving),
                                        )
                                    }
                                )
                        rows.append(row)
                        previous, prior_gray = small, gray
                        scene_history.commit(event)
                    measured = [r for r in rows if not r["reset"]]
                    summary = dict(
                        clip=name,
                        frames=len(rows),
                        accepted=float(np.mean([r["accepted"] for r in measured])),
                        gpu_ms=float(np.median([r["gpu_ms"] for r in measured])),
                        error_px=[
                            {
                                zone: float(
                                    np.mean(
                                        [
                                            r["error_px"][k][zone]
                                            for r in measured
                                            if r["error_px"][k][zone] is not None
                                        ]
                                    )
                                )
                                for zone in ("mean", "edge", "moving")
                            }
                            for k in range(2)
                        ],
                    )
                    report["clips"].append(dict(summary=summary, rows=rows))
                    print(json.dumps(summary), flush=True)
    report["passed"] = True
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
