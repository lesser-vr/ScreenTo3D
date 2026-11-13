"""Quality-change comparison; exact depth history plus bounded pixel-error gates."""
import argparse
from contextlib import ExitStack
from dataclasses import replace
import json
import math
import time
from pathlib import Path
import cv2
import numpy as np

from screento3d_app.desktop_jobs import BUNDLE
from screento3d_app.desktop_jobs import ROOT
from screento3d_app.resources import configure_resource_root
from screento3d_app.live_policy import resolve_live
from screento3d_app.live_texture_pool import LiveTexturePool
from screento3d_app.live_gpu_texture import LiveGpuTexture
from half_render_trial_worker import DLL, SHA256
from public_test_media import PublicFrames


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--layouts", default="half-sbs,half-tb")
    parser.add_argument("--production", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    layouts = args.layouts.split(",")
    if any(layout not in ("half-sbs", "half-tb") for layout in layouts):
        raise ValueError("Half layout comparison required")
    configure_resource_root(BUNDLE)
    from screento3d_app.trt_backend import DepthEngine
    rows = []
    report = dict(rows=rows, limits=dict(rgb_mae=1.0, pixel_over8_fraction=.01,
                                        edge_over8_fraction=.05, depth_max=0),
                  contract="Full-resolution eyes packed to Half versus edge-aware Half-resolution synthesis",
                  stereo_comfort_verified=False)
    with DepthEngine() as engine:
        for w, h in ((1920, 1080), (3840, 2160)):
            for layout in layouts:
                policy = replace(resolve_live("performance", strength=.5), stereo_layout=layout)
                with ExitStack() as stack:
                    original = LiveTexturePool.library_path, LiveTexturePool.library_sha256
                    try:
                        LiveTexturePool.library_path = ROOT / "out/half-render-reference/live_texture_runtime.dll"
                        LiveTexturePool.library_sha256 = "e1081f3c50dfe56cef0dcff79c4e7e568e8830e8299b1e7e616f9dec4898a597"
                        baseline = stack.enter_context(LiveGpuTexture(w, h, policy, engine, diagnostic=True))
                        LiveTexturePool.library_path, LiveTexturePool.library_sha256 = (
                            original if args.production else (DLL, SHA256))
                        trial = stack.enter_context(LiveGpuTexture(w, h, policy, engine, diagnostic=True))
                    finally:
                        LiveTexturePool.library_path, LiveTexturePool.library_sha256 = original
                    for renderer in (baseline, trial):
                        renderer.configure_live_quality("detail")
                    for name in ("FloorballGame", "OfficeWalk", "ParkingGarage"):
                        source = PublicFrames(name, 360)
                        for renderer in (baseline, trial):
                            renderer.reset()
                        for index, offset in enumerate((0, 0, 1, 2, 60, 120, 180)):
                            frame = cv2.resize(source[offset], (w, h))
                            outputs, depths = [], []
                            for renderer in (baseline, trial):
                                renderer.source_ns = 1_000_000_000 + index * 16_666_667
                                renderer.set_same_input(index == 1)
                                renderer.slot = 0
                                slot, depth = renderer.render(frame, renderer.infer(frame), diagnostic=True)
                                pixels = np.empty((renderer.pool.height, renderer.pool.width, 4), np.uint8)
                                renderer.pool.check(renderer.pool.dll.live_pool_readback(
                                    renderer.pool.handle, slot, pixels.ctypes.data))
                                outputs.append(pixels[:, :, :3].copy())
                                depths.append(depth)
                            expected, actual = outputs
                            difference = np.abs(actual.astype(np.int16) - expected.astype(np.int16))
                            edges = cv2.Canny(cv2.cvtColor(expected, cv2.COLOR_RGB2GRAY), 80, 160)
                            edges = cv2.dilate(edges, np.ones((3, 3), np.uint8)) != 0
                            over = np.any(difference > 8, axis=2)
                            mse = float(np.mean(difference.astype(np.float32) ** 2))
                            row = dict(size=[w,h], layout=layout, source=name, frame=offset,
                                depth_max=float(np.abs(depths[0]-depths[1]).max()),
                                rgb_mae=float(difference.mean()),
                                pixel_over8_fraction=float(over.mean()),
                                edge_over8_fraction=float(over[edges].mean()) if edges.any() else 0,
                                psnr=10*math.log10(255**2/mse) if mse else None,
                                baseline_projection_ms=sum(float(v) for v in baseline.projection_ms),
                                trial_projection_ms=sum(float(v) for v in trial.projection_ms))
                            row["within_limits"] = all(row[k] <= limit for k, limit in report["limits"].items())
                            rows.append(row)
                            if offset == 60:
                                for variant, pixels in zip(("baseline", "trial"), outputs):
                                    cv2.imwrite(str(args.output/f"{name}-{w}-{layout}-{variant}.png"),
                                                cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR))
                            print(json.dumps(row), flush=True)
    report["within_limits"] = all(r["within_limits"] for r in rows)
    (args.output/"report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
