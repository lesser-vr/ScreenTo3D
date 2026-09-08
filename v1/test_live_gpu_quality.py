"""Candidate numerical gate, not human/VR acceptance. No media is published."""

import argparse
import json
import os
import threading
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
import cv2
import numpy as np
from depthsbs_app.desktop_jobs import BUNDLE
from depthsbs_app.resources import configure_resource_root


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=360)
    parser.add_argument("--suite", choices=("public", "scroll", "all"), default="all")
    parser.add_argument("--compare-serial", action="store_true")
    parser.add_argument("--compare-texture", action="store_true")
    parser.add_argument("--compare-publish", action="store_true")
    parser.add_argument("--compare-pool", action="store_true")
    parser.add_argument("--compare-runtime", action="store_true")
    parser.add_argument("--pinned-input", action="store_true")
    args = parser.parse_args()
    args.compare_publish = args.compare_publish or args.compare_pool
    args.compare_texture = args.compare_texture or args.compare_publish
    args.output.mkdir(parents=True, exist_ok=False)
    configure_resource_root(BUNDLE)
    from depthsbs_app.trt_backend import DepthEngine, _cuda, cudart
    from depthsbs_app.pipeline import StereoSynthesizer, preprocess
    from depthsbs_app.stereo import guide_depth
    from depthsbs_app.live_projection import LiveProjection
    from depthsbs_app.live_gpu_candidate import LiveGpuCandidate
    from depthsbs_app.live_policy import resolve_live
    from depthsbs_app.live_host_bridge import capture_rgb, publish_rgb
    if args.pinned_input:
        from depthsbs_app.live_pinned_input import LiveGpuPinnedCandidate

        LiveGpuCandidate = LiveGpuPinnedCandidate

    report = {
        "limits": dict(
            depth_mae=1e-6, depth_max=1e-4, rgb_mae=0.05, rgb_changed_fraction=0.001
        ),
        "cases": [],
    }
    from public_test_media import prepare, PublicFrames, SOURCES

    report["public_sources"] = prepare()
    from depthsbs_app.live_gpu_candidate import DLL_SHA256, DEFAULT_RESOLVE

    report["dll_sha256"] = DLL_SHA256
    report["resolve_impl"] = os.environ.get("DEPTHSBS_LIVE_RESOLVE", DEFAULT_RESOLVE)
    report["compare_serial"] = args.compare_serial
    report["compare_texture"] = args.compare_texture
    report["compare_publish"] = args.compare_publish
    report["compare_pool"] = args.compare_pool
    report["compare_runtime"] = args.compare_runtime
    report["pinned_input"] = args.pinned_input
    if args.compare_runtime:
        from depthsbs_app.live_texture_pool import RUNTIME_SHA256

        report["runtime_dll_sha256"] = RUNTIME_SHA256
    if args.compare_texture:
        from texture_projection_oracle import (
            TEXTURE_SHA256,
            PUBLISH_SHA256,
            POOL_SHA256,
        )

        report["texture_dll_sha256"] = (
            POOL_SHA256
            if args.compare_pool
            else PUBLISH_SHA256
            if args.compare_publish
            else TEXTURE_SHA256
        )
    report["live_temporal_transition"] = resolve_live(
        "balanced"
    ).temporal_depth_transition
    rng = np.random.default_rng(246)
    scenes = [(name, PublicFrames(name, args.frames)) for name in SOURCES]
    y, x = np.indices((360, 640))
    moving = []
    for index in range(6):
        f = np.full((360, 640, 3), (30, 110, 60), np.uint8)
        f[60:300, 150 + index * 12 : 330 + index * 12] = (200, 160, 100)
        f[80:280, 335 + index * 12 : 337 + index * 12] = (180, 120, 90)
        if index == 4:
            f = 255 - f
        moving.append(f)
    scenes += [
        ("flat-thin-cut", moving),
        (
            "random-cut",
            [rng.integers(0, 256, (180, 320, 3), dtype=np.uint8) for _ in range(3)],
        ),
    ]
    if args.suite == "scroll":
        scenes = []
    if args.suite in ("scroll", "all"):
        from scroll_test_frames import ScrollFrames

        scenes.append(("generated-scroll-text", ScrollFrames()))
    with DepthEngine() as engine:
        for name, frames in scenes:
            height, width = frames[0].shape[:2]
            for mode in ("performance", "balanced", "video-quality"):
                policy = resolve_live(mode)
                with (
                    LiveProjection(width, height) as projection,
                    LiveGpuCandidate(width, height, policy, engine) as gpu,
                    ExitStack() as extra,
                ):
                    serial = None
                    texture = None
                    runtime = runtime_image = None
                    if args.compare_runtime:
                        from depthsbs_app.live_gpu_texture import LiveGpuTexture

                        runtime = extra.enter_context(
                            LiveGpuTexture(
                                width, height, policy, engine, diagnostic=True
                            )
                        )
                        runtime_image = np.empty((height, width * 2, 4), np.uint8)
                    if args.compare_texture:
                        from texture_projection_oracle import TextureProjectionOracle

                        texture = extra.enter_context(
                            TextureProjectionOracle(
                                gpu,
                                publish=args.compare_publish,
                                pool=args.compare_pool,
                            )
                        )
                    if args.compare_serial:
                        assert gpu.resolve_impl == "parallel"
                        with patch.dict(
                            os.environ, {"DEPTHSBS_LIVE_RESOLVE": "serial"}
                        ):
                            serial = extra.enter_context(
                                LiveGpuCandidate(width, height, policy, engine)
                            )
                    ref = StereoSynthesizer(
                        width,
                        height,
                        policy,
                        projection,
                        paired_projection=projection.project_pair,
                    )
                    reference_guide = []

                    def capture_guide(*args, **kwargs):
                        value = guide_depth(*args, **kwargs)
                        reference_guide[:] = [value.copy()]
                        return value

                    for index, frame in enumerate(frames):
                        tensor = preprocess(frame)
                        raw = engine.infer(tensor)
                        with patch(
                            "depthsbs_app.pipeline.guide_depth",
                            side_effect=capture_guide,
                        ):
                            expected = ref.render(frame, raw)
                        token = gpu.infer(frame)
                        # Verify preprocessing independently, outside benchmark timing.
                        actual_tensor = np.empty(tensor.shape, dtype=np.float32)
                        _cuda(
                            cudart.cudaMemcpyAsync(
                                actual_tensor.ctypes.data,
                                engine.device_input,
                                engine.input_bytes,
                                cudart.cudaMemcpyKind.cudaMemcpyDeviceToHost,
                                engine.stream,
                            )
                        )
                        _cuda(cudart.cudaStreamSynchronize(engine.stream))
                        actual, aligned = gpu.render(frame, token, diagnostic=True)
                        texture_exact = texture.compare(actual) if texture else None
                        serial_exact = (
                            np.array_equal(actual, serial.render(frame, token))
                            if serial is not None
                            else None
                        )
                        runtime_exact = (
                            compare_runtime(
                                runtime, runtime_image, actual, frame, token
                            )
                            if runtime is not None
                            else None
                        )
                        # Exact host-bridge checks are outside performance timing.
                        bgra_input = cv2.cvtColor(frame, cv2.COLOR_RGB2BGRA)
                        input_exact = np.array_equal(
                            capture_rgb(bgra_input, width, height), frame
                        )
                        bgra_output = np.empty((height, width * 2, 4), np.uint8)
                        publish_rgb(bgra_output, actual)
                        output_exact = np.array_equal(
                            bgra_output, cv2.cvtColor(actual, cv2.COLOR_RGB2BGRA)
                        )
                        diff = np.abs(aligned - reference_guide[0])
                        pixel = np.abs(
                            actual.astype(np.int16) - expected.astype(np.int16)
                        )
                        row = dict(
                            scene=name,
                            mode=mode,
                            frame=index,
                            preprocess_max=float(
                                np.max(np.abs(actual_tensor - tensor))
                            ),
                            depth_mae=float(diff.mean()),
                            depth_max=float(diff.max()),
                            rgb_mae=float(pixel.mean()),
                            rgb_changed_fraction=float(
                                np.mean(np.any(pixel != 0, axis=2))
                            ),
                            cpu_refinements=gpu.cpu_refinements,
                            texture_exact=texture_exact,
                            runtime_exact=runtime_exact,
                            host_bridge_exact=bool(input_exact and output_exact),
                            serial_exact=bool(serial_exact)
                            if serial is not None
                            else None,
                        )
                        row["pass"] = (
                            row["host_bridge_exact"]
                            and (texture is None or row["texture_exact"])
                            and (serial is None or row["serial_exact"])
                            and (runtime is None or row["runtime_exact"])
                            and row["preprocess_max"] == 0
                            and all(row[k] <= v for k, v in report["limits"].items())
                        )
                        report["cases"].append(row)
                        if name in SOURCES and index in (
                            2,
                            args.frames // 2,
                            args.frames - 1,
                        ):
                            for label, image in [
                                ("reference", expected),
                                ("candidate", actual),
                            ]:
                                cv2.imwrite(
                                    str(
                                        args.output
                                        / f"{name}-{mode}-{index}-{label}.png"
                                    ),
                                    cv2.cvtColor(image, cv2.COLOR_RGB2BGR),
                                )
                        if index % 30 == 0 or not row["pass"]:
                            print(json.dumps(row), flush=True)
                            (args.output / "report.json").write_text(
                                json.dumps(report, indent=2)
                            )
                    errors = []
                    thread = threading.Thread(target=lambda: cross_thread(gpu, errors))
                    thread.start()
                    thread.join()
                    assert errors == ["RuntimeError"]
                    # Same-input reuse and explicit reset equal a new renderer.
                    frame = frames[-1]
                    token = gpu.infer(frame)
                    for _ in range(2):
                        reused = gpu.render(frame, token)
                        if runtime is not None:
                            assert compare_runtime(
                                runtime, runtime_image, reused, frame, token
                            )
                    gpu.reset()
                    reset = gpu.render(frame, token)
                    if runtime is not None:
                        runtime.reset()
                        assert compare_runtime(
                            runtime, runtime_image, reset, frame, token
                        )
                    with LiveGpuCandidate(width, height, policy, engine) as fresh:
                        assert np.array_equal(reset, fresh.render(frame, token))
                    newer = gpu.infer(frame)
                    try:
                        gpu.render(frame, token)
                    except RuntimeError:
                        pass
                    else:
                        raise AssertionError("Stale depth accepted")
                    gpu.render(frame, newer)
                    if runtime is not None:
                        try:
                            runtime.render(frame, token)
                        except RuntimeError:
                            pass
                        else:
                            raise AssertionError("Native renderer accepted stale depth")
        report["passed"] = all(row["pass"] for row in report["cases"])
        report["ownership_reset_reuse"] = True
        report["native_reset_reuse_stale"] = args.compare_runtime
        (args.output / "report.json").write_text(json.dumps(report, indent=2))
    assert report["passed"], "Candidate numerical gate failed; do not promote default"


def cross_thread(gpu, errors):
    try:
        gpu.reset()
    except Exception as error:
        errors.append(type(error).__name__)


def compare_runtime(runtime, image, expected, frame, token):
    runtime.slot = runtime.frames % 2
    slot = runtime.render(frame, token)
    runtime.pool.check(
        runtime.pool.dll.live_pool_readback(
            runtime.pool.handle, slot, image.ctypes.data
        )
    )
    return bool(
        np.array_equal(image[:, :, :3], expected) and np.all(image[:, :, 3] == 255)
    )


if __name__ == "__main__":
    main()
