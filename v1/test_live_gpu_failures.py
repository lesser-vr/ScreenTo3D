"""Real GPU candidate lifecycle/error checks, without screen capture."""

import ctypes
import json
import threading
from pathlib import Path
import numpy as np
from depthsbs_app.desktop_jobs import BUNDLE
from depthsbs_app.resources import configure_resource_root


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=Path("out/live-gpu-speed/failures.json")
    )
    parser.add_argument("--native", action="store_true")
    parser.add_argument("--guide-candidate", choices=("hybrid", "promoted"))
    parser.add_argument("--pinned-input", action="store_true")
    args = parser.parse_args()
    if args.pinned_input and not args.native:
        parser.error("--pinned-input requires --native")
    configure_resource_root(BUNDLE)
    from depthsbs_app.trt_backend import DepthEngine, _cuda, cudart
    from depthsbs_app import live_gpu_candidate as gpu_module
    from depthsbs_app.live_policy import resolve_live

    if args.guide_candidate == "hybrid":
        from depthsbs_app.live_guide_hybrid_worker import candidate_manifest

    elif args.guide_candidate == "promoted":
        from depthsbs_app.live_guide_promoted_worker import candidate_manifest

    input_candidate = None
    if args.pinned_input:
        from depthsbs_app.live_pinned_input_worker import candidate_manifest as pinned

        input_candidate = pinned()
    if args.guide_candidate:
        candidate = candidate_manifest()
        gpu_module.DLL_PATH = Path(candidate["dll"])
        gpu_module.DLL_SHA256 = candidate["dll_sha256"]
    from depthsbs_app.live_gpu_candidate import LiveGpuCandidate

    if args.native:
        if args.guide_candidate:
            from depthsbs_app import live_gpu_texture as texture_module

            texture_module.DLL_SHA256 = candidate["dll_sha256"]
            texture_module.BORROWED_LAYOUT_SHA256 = candidate["dll_sha256"]
        from depthsbs_app.live_gpu_texture import LiveGpuTexture

        LiveGpuCandidate = LiveGpuTexture
        if args.pinned_input:
            from depthsbs_app.live_pinned_input import LiveGpuPinnedTexture

            LiveGpuCandidate = LiveGpuPinnedTexture

    results = []
    frame = np.full((180, 320, 3), 127, np.uint8)
    for index in range(5):
        if args.native:
            frame = (
                np.full((180, 320, 3), 127, np.uint8)
                if index % 2 == 0
                else np.random.default_rng(index).integers(
                    0, 256, (180, 320, 3), dtype=np.uint8
                )
            )
        with DepthEngine() as engine:
            with LiveGpuCandidate(320, 180, resolve_live("balanced"), engine) as gpu:
                token = gpu.infer(frame)
                if args.native:
                    gpu.slot = 0
                gpu.render(frame, token)
                token = gpu.infer(frame)
                raw = np.full((1, 518, 518), np.nan, np.float32)
                _cuda(
                    cudart.cudaMemcpyAsync(
                        engine.device_output,
                        raw.ctypes.data,
                        raw.nbytes,
                        cudart.cudaMemcpyKind.cudaMemcpyHostToDevice,
                        engine.stream,
                    )
                )
                try:
                    gpu.render(frame, token)
                except RuntimeError as error:
                    assert "Non-finite" in str(error)
                    if args.native and index % 2:
                        assert "raw" in str(error)
                else:
                    raise AssertionError("Non-finite depth accepted")
                try:
                    gpu.reset()
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("Failed context reused")
            assert not gpu.handle.value
            gpu.close()
            errors = []

            def close_elsewhere():
                try:
                    engine.close()
                except RuntimeError:
                    errors.append(True)

            thread = threading.Thread(target=close_elsewhere)
            thread.start()
            thread.join()
            assert errors == [True]
        try:
            token.validate()
        except RuntimeError:
            pass
        else:
            raise AssertionError("Closed engine depth accepted")
        results.append(
            dict(
                cycle=index,
                nan_rejected=True,
                poisoned_context=True,
                idempotent_close=True,
                wrong_thread_close=True,
                closed_token=True,
            )
        )
    # Boundary rejection occurs without allocation or invalid pointer submission.
    with DepthEngine() as engine:
        for width, height in [(0, 180), (4097, 180), (320, 2161)]:
            try:
                LiveGpuCandidate(width, height, resolve_live("balanced"), engine)
            except ValueError:
                pass
            else:
                raise AssertionError("Invalid dimensions accepted")
        with LiveGpuCandidate(320, 180, resolve_live("balanced"), engine) as gpu:
            empty = ctypes.c_void_p()
            assert (
                gpu.dll.live_create(ctypes.byref(empty), 0, 180, int(engine.stream))
                != 0
            )
            assert not empty.value
    target = args.output
    target.parent.mkdir(parents=True, exist_ok=True)
    report = results
    if args.guide_candidate or args.pinned_input:
        report = {
            "candidate": (
                candidate
                if args.guide_candidate
                else input_candidate
            ),
            "native": args.native,
            "cycles": results,
        }
    target.write_text(json.dumps(report, indent=2))
    print(json.dumps(report))


if __name__ == "__main__":
    main()
