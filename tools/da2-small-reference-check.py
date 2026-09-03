import argparse
import json
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort


SHAPE = (1, 3, 518, 518)
OUTPUT_SHAPE = (1, 518, 518)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("model", type=Path)
    parser.add_argument("input", type=Path)
    parser.add_argument("tensorrt_output", type=Path)
    arguments = parser.parse_args()

    input_tensor = np.fromfile(arguments.input, dtype="<f4").reshape(SHAPE)
    session = ort.InferenceSession(
        str(arguments.model), providers=["CPUExecutionProvider"]
    )
    started = time.perf_counter()
    reference = session.run(
        ["predicted_depth"], {"pixel_values": input_tensor}
    )[0]
    reference_ms = (time.perf_counter() - started) * 1000.0
    if reference.shape != OUTPUT_SHAPE or not np.isfinite(reference).all():
        raise ValueError("invalid FP32 reference output")

    payload = json.loads(arguments.tensorrt_output.read_text(encoding="utf-8"))
    candidate = np.asarray(payload[0]["values"], dtype=np.float32).reshape(OUTPUT_SHAPE)
    error = candidate - reference
    absolute_error = np.abs(error)
    mae = float(absolute_error.mean())
    rmse = float(np.sqrt(np.mean(error * error)))
    max_absolute_error = float(absolute_error.max())
    mean_relative_error = float(
        (absolute_error / np.maximum(np.abs(reference), 1.0e-6)).mean()
    )
    correlation = float(np.corrcoef(reference.ravel(), candidate.ravel())[0, 1])

    thresholds = {
        "mae": 0.01,
        "rmse": 0.015,
        "max_absolute_error": 0.05,
        "mean_relative_error": 0.01,
        "minimum_correlation": 0.999,
    }
    passed = (
        mae <= thresholds["mae"]
        and rmse <= thresholds["rmse"]
        and max_absolute_error <= thresholds["max_absolute_error"]
        and mean_relative_error <= thresholds["mean_relative_error"]
        and correlation >= thresholds["minimum_correlation"]
    )
    result = {
        "schema_version": 1,
        "shape": list(OUTPUT_SHAPE),
        "reference_ms": reference_ms,
        "mae": mae,
        "rmse": rmse,
        "max_absolute_error": max_absolute_error,
        "mean_relative_error": mean_relative_error,
        "correlation": correlation,
        "thresholds": thresholds,
        "fp32_oracle_validated": passed,
        "official_checkpoint_validated": False,
    }
    print(json.dumps(result, indent=2))
    if not passed:
        raise SystemExit("TensorRT output exceeded the FP32 numerical error budget")


if __name__ == "__main__":
    main()
