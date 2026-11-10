"""Create deterministic stereo midpoint fixtures; does not run NVIDIA VFG."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np


def scene(width: int, height: int) -> np.ndarray:
    """A textured plane with thin edges, with margins for exact integer crops."""
    rng = np.random.default_rng(20261105)
    image = np.empty((height, width + 64, 3), dtype=np.uint8)
    image[:] = (28, 35, 44)
    for _ in range(180):
        x, y = rng.integers(0, width + 64), rng.integers(0, height)
        size = int(rng.integers(2, max(3, height // 14)))
        color = tuple(int(c) for c in rng.integers(45, 240, 3))
        cv2.rectangle(image, (int(x), int(y)), (int(x + size), int(y + size)), color, -1)
    for x in range(0, width + 64, 43):
        cv2.line(image, (x, 0), (x + height // 3, height - 1), (225, 180, 70), 1)
    return image


def stereo(plane: np.ndarray, width: int, offset: int) -> np.ndarray:
    # Right(x) = Left(x + 12) away from the non-overlapping borders.
    left = plane[:, offset : offset + width]
    right = plane[:, offset + 12 : offset + 12 + width]
    return np.concatenate((left, right), axis=1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = {
        "schema": 1,
        "kind": "synthetic_input_only_not_vfg_output",
        "pixel_format": "RGB8 PNG (decode BGRA8/RGBA8 for VFG)",
        "seed": 20261105,
        "right_eye_disparity_px": 12,
        "cases": [],
    }
    for width, height in ((320, 180), (1920, 1080), (3840, 2160)):
        plane = scene(width, height)
        previous = stereo(plane, width, 16)
        midpoint = stereo(plane, width, 20)
        current = stereo(plane, width, 24)
        # Verify exact geometric ground truth before writing the fixture.
        assert np.array_equal(midpoint[:, 12:width], midpoint[:, width:2 * width - 12])
        assert np.array_equal(previous[:, 4:width], midpoint[:, :width - 4])
        for name, frames, manual_cut in (
            ("translation", (previous, midpoint, current), False),
            ("identity", (previous, previous, previous), False),
            ("cut", (previous, 255 - current, 255 - current), True),
        ):
            folder = args.output / f"{2 * width}x{height}" / name
            folder.mkdir(parents=True)
            files = {}
            for role, pixels in zip(("previous", "expected", "current"), frames, strict=True):
                path = folder / f"{role}.png"
                if not cv2.imwrite(str(path), pixels, [cv2.IMWRITE_PNG_COMPRESSION, 3]):
                    raise RuntimeError(f"Could not write {path}")
                decoded = cv2.imread(str(path), cv2.IMREAD_COLOR)
                if decoded is None or not np.array_equal(pixels, decoded):
                    raise RuntimeError(f"Lossless round trip failed: {path}")
                files[role] = {
                    "path": path.relative_to(args.output).as_posix(),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            manifest["cases"].append({
                "case": name, "width": 2 * width, "height": height,
                "eye_width": width, "multiplier": 2, "frame_index": 1,
                "manual_shot_change": manual_cut, "files": files,
                "expected_semantics": "copy current" if manual_cut else "true midpoint",
            })
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"cases": len(manifest["cases"]), "png_round_trips": 27,
                      "vfg_executed": False, "manifest": str(args.output / "manifest.json")}))


if __name__ == "__main__":
    main()
