import argparse
import json
import math
from pathlib import Path

import numpy as np


WIDTH = 518
HEIGHT = 518
MEAN = np.asarray([0.485, 0.456, 0.406], dtype=np.float32)[:, None, None]
STD = np.asarray([0.229, 0.224, 0.225], dtype=np.float32)[:, None, None]


def generate_input(path: Path) -> None:
    x = np.linspace(0.0, 1.0, WIDTH, dtype=np.float32)[None, :]
    y = np.linspace(0.0, 1.0, HEIGHT, dtype=np.float32)[:, None]
    rgb = np.stack(
        (
            np.broadcast_to(x, (HEIGHT, WIDTH)),
            np.broadcast_to(y, (HEIGHT, WIDTH)),
            (np.broadcast_to(x, (HEIGHT, WIDTH)) + np.broadcast_to(y, (HEIGHT, WIDTH))) * 0.5,
        ),
        axis=0,
    )
    normalized = ((rgb - MEAN) / STD)[None, ...]
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized.astype("<f4", copy=False).tofile(path)


def validate_output(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if len(payload) != 1 or payload[0].get("name") != "predicted_depth":
        raise ValueError("unexpected TensorRT output tensor")
    if payload[0].get("dimensions") != "1x518x518":
        raise ValueError("unexpected predicted_depth dimensions")

    values = np.asarray(payload[0].get("values"), dtype=np.float32)
    expected_count = WIDTH * HEIGHT
    if values.size != expected_count:
        raise ValueError(f"unexpected output count: {values.size}")
    if not np.isfinite(values).all():
        raise ValueError("predicted_depth contains non-finite values")
    minimum = float(values.min())
    maximum = float(values.max())
    standard_deviation = float(values.std())
    if minimum < 0.0:
        raise ValueError(f"predicted_depth contains negative values: {minimum}")
    if not math.isfinite(standard_deviation) or standard_deviation <= 1.0e-6:
        raise ValueError("predicted_depth is effectively constant")

    return {
        "schema_version": 1,
        "tensor": "predicted_depth",
        "shape": [1, HEIGHT, WIDTH],
        "element_count": int(values.size),
        "finite": True,
        "minimum": minimum,
        "maximum": maximum,
        "mean": float(values.mean()),
        "standard_deviation": standard_deviation,
        "inference_validated": True,
        "reference_accuracy_validated": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate")
    generate.add_argument("path", type=Path)
    validate = subparsers.add_parser("validate")
    validate.add_argument("path", type=Path)
    arguments = parser.parse_args()

    if arguments.command == "generate":
        generate_input(arguments.path)
        return
    print(json.dumps(validate_output(arguments.path), indent=2))


if __name__ == "__main__":
    main()
