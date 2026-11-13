"""Isolated public-video GPU-to-texture worker, not the desktop capture worker."""

import ctypes as ct
import os
import sys

import cv2
import numpy as np

from screento3d_app.desktop_jobs import BUNDLE
from screento3d_app.resources import configure_resource_root
from screento3d_app.live_policy import resolve_live
from screento3d_app.live_gpu_candidate import LiveGpuCandidate
from screento3d_app.stereo import refine_flat_background
from texture_projection_oracle import TextureProjectionOracle
from public_test_media import PublicFrames


def publish_frame(gpu, surface, frame, slot, clear):
    gpu._owner()
    policy = gpu.policy
    token = None
    refined = None
    if not clear:
        token = gpu.infer(frame)
        token.validate()
        scene = gpu.inspect_scene(frame)
        reset = gpu.reset_pending or scene.cut
        background = gpu.needs_background(frame)
        aligned = np.empty((gpu.height, gpu.width), np.float32) if background else None
        gpu._check(
            gpu.dll.live_post(
                gpu.handle,
                frame.ctypes.data,
                token.pointer,
                policy.depth_guide_radius,
                policy.temporal_alpha,
                policy.temporal_color_threshold,
                policy.temporal_depth_threshold,
                int(reset),
                aligned.ctypes.data if aligned is not None else None,
                policy.temporal_depth_transition,
            )
        )
        if aligned is not None:
            from screento3d_app.trt_backend import _cuda, cudart

            _cuda(cudart.cudaStreamSynchronize(gpu.engine.stream))
            if not np.isfinite(aligned).all():
                raise RuntimeError("Non-finite aligned depth")
            refined = refine_flat_background(
                frame,
                aligned,
                tolerance=policy.flat_background_tolerance,
                minimum_coverage=policy.flat_background_min_coverage,
                radius=policy.depth_guide_radius,
            )
            if refined is aligned:
                refined = None
    surface._check(
        surface.dll.live_texture_publish(
            surface.handle,
            gpu.handle,
            policy.convergence,
            max(1.0, gpu.width * policy.divergence),
            int(policy.conservative_stereo_coverage),
            refined.ctypes.data if refined is not None else None,
            slot,
            int(clear),
        )
    )
    if token is not None:
        gpu.engine.complete_device(token)
        gpu.reset_pending = False
        gpu.scene_history.commit(scene)
        gpu.frames += 1


from screento3d_app.environment import get as app_env

def main():
    if len(sys.argv) != 4:
        raise ValueError("Expected parent PID and SBS dimensions")
    parent, width, height = map(int, sys.argv[1:])
    if parent != os.getppid() or width % 2:
        raise ValueError("Invalid parent or dimensions")
    configure_resource_root(BUNDLE)
    from screento3d_app.trt_backend import DepthEngine

    frames = PublicFrames("FloorballGame", 360)
    iterator = iter(frames)
    with (
        DepthEngine() as engine,
        LiveGpuCandidate(width // 2, height, resolve_live("balanced"), engine) as gpu,
        TextureProjectionOracle(gpu, publish=True) as surface,
    ):
        surface.dll.live_texture_export.argtypes = [
            ct.c_void_p,
            ct.c_ulong,
            ct.c_void_p,
            ct.c_void_p,
            ct.c_void_p,
        ]
        handles = (ct.c_ulonglong * 2)()
        low, high = ct.c_ulong(), ct.c_long()
        surface._check(
            surface.dll.live_texture_export(
                surface.handle, parent, handles, ct.byref(low), ct.byref(high)
            )
        )
        print(
            f"READY {width} {height} {low.value} {high.value} {handles[0]} {handles[1]}",
            flush=True,
        )
        commands = 0
        while True:
            line = sys.stdin.readline(256)
            if not line:
                break
            if len(line) > 255 or not line.endswith("\n"):
                raise ValueError("Oversized or incomplete command")
            if line == "STOP\n":
                break
            parts = line.split()
            if len(parts) != 4 or parts[0] != "FRAME":
                raise ValueError("Invalid command")
            slot, frame_id, clear = map(int, parts[1:])
            if slot not in (0, 1) or frame_id < 0 or clear not in (0, 1):
                raise ValueError("Invalid frame descriptor")
            commands += 1
            if app_env("SCREENTO3D_TEXTURE_TEST_CRASH") and commands == 10:
                os._exit(42)
            frame = None
            if not clear:
                try:
                    frame = next(iterator)
                except StopIteration:
                    iterator = iter(frames)
                    frame = next(iterator)
                    gpu.reset()
                if frame.shape[:2] != (height, width // 2):
                    frame = cv2.resize(
                        frame, (width // 2, height), interpolation=cv2.INTER_CUBIC
                    )
                frame = np.ascontiguousarray(frame)
            publish_frame(gpu, surface, frame, slot, clear)
            print(f"FRAME {slot} {frame_id}", flush=True)
        iterator.close()
    print("STOPPED", flush=True)


if __name__ == "__main__":
    main()
