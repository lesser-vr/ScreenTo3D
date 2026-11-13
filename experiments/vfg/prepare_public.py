"""Prepare held-out native Base FP16 SBS midframes from three pinned public clips."""
from contextlib import ExitStack
from dataclasses import asdict, replace
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil

import cv2
import numpy as np
import torch

from screento3d_app.da2_base import binding
from screento3d_app.desktop_jobs import ROOT, BUNDLE
from screento3d_app.gpu_frame import GpuFrame
from screento3d_app.live_policy import resolve_live
from screento3d_app.live_source_gpu_texture import LiveSourceGpuTexture
from screento3d_app.resources import configure_resource_root
from public_test_media import PublicFrames, ATTRIBUTION, CORPUS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    output = parser.parse_args().output.resolve()
    output.mkdir(exist_ok=False)
    configure_resource_root(BUNDLE)
    cv2.setNumThreads(1)
    torch.set_num_threads(4)
    os.environ["SCREENTO3D_BASE_GRAPH"] = "0"
    os.environ["SCREENTO3D_BASE_INPUT"] = "gpu"
    policy = replace(resolve_live("balanced"), depth_backend="da2-base")
    clips = ("FloorballGame", "OfficeWalk", "ParkingGarage")
    width, height = 3840, 2160
    provenance = {"attribution": ATTRIBUTION, "policy": asdict(policy), "sources": {},
                  "scope": "native Base FP16 readback; 60fps histories; endpoints 60/62, held-out 61; no native FPS measurement",
                  "resize": "prepared 1080p public preview upscaled to 4K using OpenCV linear",
                  "warmup_frames": [54, 55, 56, 57, 58, 59]}
    with ExitStack() as stack:
        runtime = Path("C:/TensorRT/TensorRT-11.2.1.2/bin")
        stack.enter_context(os.add_dll_directory(str(runtime)))
        backend = binding(ROOT / "out/da2-base-local", runtime, device_depth=True)
        backend.input_validator(dict(width=width, height=height))
        engine = stack.enter_context(backend.engine_factory(None))
        provenance["plan_sha256"] = engine.plan_hash
        for clip in clips:
            provenance["sources"][clip] = json.loads((CORPUS / f"{clip}.json").read_text())
            folder = output / clip
            folder.mkdir()
            with LiveSourceGpuTexture(width, height, policy, engine, diagnostic=True) as renderer:
                for index, rgb in enumerate(PublicFrames(clip, 63)):
                    if index < 54:
                        continue
                    rgb = cv2.resize(rgb, (width, height), interpolation=cv2.INTER_LINEAR)
                    with torch.inference_mode(), torch.cuda.stream(engine.stream):
                        frame = GpuFrame(torch.from_numpy(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGRA)).cuda(), engine)
                    renderer.slot = index % 2
                    slot = renderer.render(frame, renderer.infer(frame))
                    # Diagnostic readback also acknowledges/releases this output slot.
                    pixels = np.empty((height, width * 2, 4), np.uint8)
                    renderer.pool.check(renderer.pool.dll.live_pool_readback(renderer.pool.handle, slot, pixels.ctypes.data))
                    if not np.all(pixels[:, :, 3] == 255) or engine.pending_device is not None:
                        raise RuntimeError("Native output completion failed")
                    if index >= 60:
                        if not cv2.imwrite(str(folder / f"frame{index}.png"), cv2.cvtColor(pixels[:, :, :3], cv2.COLOR_RGB2BGR)):
                            raise RuntimeError("Native fixture write failed")
            print(f"native inputs complete: {clip}", flush=True)
    for i, clip in enumerate(clips):
        folder = output / clip
        cases = []
        for name, sources in (
            ("identity", [folder / "frame60.png"] * 3),
            ("translation", [folder / f"frame{k}.png" for k in (60, 61, 62)]),
            ("cut", [folder / "frame60.png"] + [output / clips[(i + 1) % 3] / "frame62.png"] * 2),
        ):
            files = {}
            target = folder / name
            target.mkdir()
            for role, source in zip(("previous", "expected", "current"), sources, strict=True):
                path = target / f"{role}.png"
                shutil.copyfile(source, path)
                files[role] = {"path": path.relative_to(folder).as_posix(),
                               "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            cases.append(dict(case=name, width=width * 2, height=height, files=files))
        (folder / "manifest.json").write_text(json.dumps(dict(kind="public_native_sbs", cases=cases), indent=2))
    (output / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
