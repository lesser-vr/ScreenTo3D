"""Single public frame: resized depth and percentile neighborhood attribution."""

import ctypes as ct
import argparse
import json
from pathlib import Path
import cv2
import numpy as np
from public_test_media import PublicFrames, prepare
from depthsbs_app.desktop_jobs import BUNDLE
from depthsbs_app.resources import configure_resource_root


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare()
    configure_resource_root(BUNDLE)
    from depthsbs_app.trt_backend import DepthEngine, _cuda, cudart
    from depthsbs_app.live_gpu_candidate import LiveGpuCandidate
    from depthsbs_app.live_policy import resolve_live

    frame = PublicFrames("OfficeWalk", 187)[186]
    with (
        DepthEngine() as engine,
        LiveGpuCandidate(1920, 1080, resolve_live("performance"), engine) as gpu,
    ):
        token = gpu.infer(frame)
        raw = np.empty((518, 518), np.float32)
        _cuda(
            cudart.cudaMemcpyAsync(
                raw.ctypes.data,
                token.pointer,
                raw.nbytes,
                cudart.cudaMemcpyKind.cudaMemcpyDeviceToHost,
                engine.stream,
            )
        )
        gpu.render(frame, token)
        resized = np.empty((1080, 1920), np.float32)
        gpu.dll.live_resize_probe.argtypes = [ct.c_void_p] * 3
        gpu._check(
            gpu.dll.live_resize_probe(gpu.handle, token.pointer, resized.ctypes.data)
        )
        ref = cv2.resize(raw, (1920, 1080), interpolation=cv2.INTER_CUBIC)
        rows = []
        for q in (0.02, 0.98):
            pos = (ref.size - 1) * q
            index = int(pos)
            rows.append(
                dict(
                    q=q,
                    pos=pos,
                    reference_neighbors=np.sort(ref.ravel())[
                        index - 2 : index + 4
                    ].tolist(),
                    gpu_neighbors=np.sort(resized.ravel())[
                        index - 2 : index + 4
                    ].tolist(),
                )
            )
        y, x = np.unravel_index(np.argmax(np.abs(resized - ref)), ref.shape)
        report = dict(
            cv2=cv2.__version__,
            numpy=np.__version__,
            max_error=float(np.max(np.abs(resized - ref))),
            mae=float(np.mean(np.abs(resized - ref))),
            worst=[int(x), int(y)],
            reference_percentile=np.percentile(ref, [2.0, 98.0]).tolist(),
            gpu_percentile=np.percentile(resized, [2.0, 98.0]).tolist(),
            neighbors=rows,
        )
        report["percentile_max"] = float(
            np.max(
                np.abs(
                    np.asarray(report["reference_percentile"])
                    - report["gpu_percentile"]
                )
            )
        )
        report["passed"] = (
            report["max_error"] <= 1e-5 and report["percentile_max"] <= 2e-6
        )
        target = args.output
        target.mkdir(parents=True, exist_ok=False)
        np.savez(target / "arrays.npz", raw=raw, reference=ref, gpu=resized)
        (target / "report.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
        assert report["passed"], "Public resize/percentile regression"


if __name__ == "__main__":
    main()
