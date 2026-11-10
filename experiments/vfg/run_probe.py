"""Run the pinned local VFG probe sequentially; no application/native-FPS claim."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SDK = ROOT / "out/vfg-sdk-1.3.0.0/VideoFX"
FIXTURES = ROOT / "out/vfg-fixtures-20261105"
EXE = ROOT / "out/vfg-probe-build/vfg_probe.exe"
PINS = {
    "bin/NVVideoEffects.dll": "2fab7e1c13ef28c2ab8f14d9dfacb5062b7b74374035af7466c58458922ec1be",
    "bin/NVCVImage.dll": "afd9b7ad335d78663126b315c50c2a8820c474ce6debeda414dd633acead949d",
    "features/nvvfxvideoframegeneration/bin/nvVFXVideoFrameGeneration.dll": "f803e891e75b1a1d9d4a42c0fffc208fa48953e6e135ce9493e935bc0044fc97",
}


def digest(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def metrics(actual: np.ndarray, expected: np.ndarray, fixed_disparity: bool = True) -> dict:
    error = np.abs(actual.astype(np.int16) - expected.astype(np.int16))
    half = actual.shape[1] // 2
    result = {
        "mae_255": float(error.mean()), "max_error_255": int(error.max()),
        "left_mae_255": float(error[:, :half].mean()),
        "right_mae_255": float(error[:, half:].mean()),
        "seam_16px_mae_255": float(error[:, half - 8:half + 8].mean()),
    }
    if fixed_disparity:
        binocular = np.abs(actual[:, 12:half].astype(np.int16) - actual[:, half:-12].astype(np.int16))
        result["disparity_aligned_mae_255"] = float(binocular.mean())
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sizes", nargs="+", choices=("640x180", "3840x1080", "3840x2160", "7680x2160"),
                        default=["640x180", "3840x1080", "7680x2160"])
    parser.add_argument("--modes", nargs="+", type=int, choices=(0, 1, 2), default=[0, 1, 2])
    parser.add_argument("--automatic-cut", action="store_true")
    parser.add_argument("--fixtures", type=Path, default=FIXTURES)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((args.fixtures / "manifest.json").read_text())
    fixed_disparity = manifest.get("right_eye_disparity_px") == 12
    provenance = {"sdk_version": "1.3.0.0", "artifacts": {}, "probe_sha256": digest(EXE)}
    for relative, expected_hash in PINS.items():
        actual_hash = digest(SDK / relative)
        if actual_hash != expected_hash:
            raise RuntimeError("VFG SDK binary differs from the tested official artifact")
        provenance["artifacts"][relative] = actual_hash
    (output / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    results = []
    for size in args.sizes:
        width, height = map(int, size.split("x"))
        raw = output / "input" / size
        expected = {}
        endpoints = {}
        for case in (c for c in manifest["cases"] if c["width"] == width and c["height"] == height):
            case_dir = raw / case["case"]
            case_dir.mkdir(parents=True)
            for role, record in case["files"].items():
                path = args.fixtures / record["path"]
                if digest(path) != record["sha256"]:
                    raise RuntimeError("Fixture hash mismatch")
                pixels = cv2.imread(str(path), cv2.IMREAD_COLOR)
                if pixels is None or pixels.shape != (height, width, 3):
                    raise RuntimeError("Invalid fixture pixels")
                if role == "expected":
                    expected[case["case"]] = pixels
                else:
                    endpoints[case["case"], role] = pixels
                    cv2.cvtColor(pixels, cv2.COLOR_BGR2RGBA).tofile(case_dir / f"{role}.rgba")
        for mode in args.modes:
            dest = output / f"{size}-mode{mode}"
            cmd = [str(EXE), str(SDK), str(raw), str(dest), str(width), str(height),
                   str(mode), str(int(args.automatic_cut))]
            env = os.environ.copy()
            env["CUDA_VISIBLE_DEVICES"] = "0"
            try:
                run = subprocess.run(cmd, capture_output=True, timeout=180, env=env)
                (output / f"{dest.name}.log").write_bytes(run.stdout + run.stderr)
                result_path = dest / "result.json"
                result = json.loads(result_path.read_text()) if result_path.exists() and result_path.stat().st_size else {"success": False, "stage": "process_failure"}
                result["returncode"] = run.returncode
                result["success"] = bool(result["success"] and run.returncode == 0)
            except subprocess.TimeoutExpired:
                result = {"success": False, "stage": "timeout", "owned_process_killed": True}
            result.update(size=size, mode=mode, automatic_cut=args.automatic_cut)
            if result["success"] and result["returncode"] == 0:
                result["gpu_median_ms"] = statistics.median(result["gpu_ms"])
                result["wall_median_ms"] = statistics.median(result["wall_ms"])
                result["quality"] = {}
                translation = None
                for name in ("identity", "translation", "cut", "after_cut"):
                    raw_output = dest / f"{name}.rgba"
                    rgba = np.fromfile(raw_output, dtype=np.uint8).reshape(height, width, 4)
                    bgr = cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)
                    reference = expected["translation" if name == "after_cut" else name]
                    case_name = "translation" if name == "after_cut" else name
                    previous = endpoints[case_name, "previous"]
                    current = endpoints[case_name, "current"]
                    result["quality"][name] = metrics(bgr, reference, fixed_disparity)
                    if manifest.get("layout") == "mono":
                        for field in ("left_mae_255", "right_mae_255", "seam_16px_mae_255"):
                            result["quality"][name].pop(field)
                    result["quality"][name].update(
                        output_previous_mae_255=float(np.abs(bgr.astype(np.int16)-previous.astype(np.int16)).mean()),
                        output_current_mae_255=float(np.abs(bgr.astype(np.int16)-current.astype(np.int16)).mean()),
                        hold_mae_255=float(np.abs(previous.astype(np.int16)-reference.astype(np.int16)).mean()),
                        blend_mae_255=float(np.abs((previous.astype(np.float32)+current)/2-reference).mean()))
                    if name == "translation":
                        translation = bgr
                    if name == "after_cut":
                        result["after_cut_equals_translation"] = bool(np.array_equal(translation, bgr))
                    if not cv2.imwrite(str(dest / f"{name}.png"), bgr):
                        raise RuntimeError("PNG output write failed")
                    raw_output.unlink()  # Owned intermediate; lossless PNG retained.
                result["cut_copies_current"] = result["quality"]["cut"]["max_error_255"] == 0
            results.append(result)
            (output / "summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
            print(json.dumps({k: v for k, v in result.items() if k not in ("quality", "gpu_ms", "wall_ms")}), flush=True)
        for case_name in ("identity", "translation", "cut"):
            for role in ("previous", "current"):
                (raw / case_name / f"{role}.rgba").unlink()
    if not all(result["success"] for result in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
