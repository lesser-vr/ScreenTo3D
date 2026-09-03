from __future__ import annotations

import argparse
from pathlib import Path

import onnx
from onnx import TensorProto, checker, helper


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    input_info = helper.make_tensor_value_info(
        "input", TensorProto.FLOAT16, [1, 3, 8, 8]
    )
    output_info = helper.make_tensor_value_info(
        "output", TensorProto.FLOAT16, [1, 3, 8, 8]
    )
    graph = helper.make_graph(
        [helper.make_node("Identity", ["input"], ["output"], name="fp16_identity")],
        "depthsbs_tensorrt11_smoke",
        [input_info],
        [output_info],
    )
    model = helper.make_model(
        graph,
        producer_name="DepthSBS",
        opset_imports=[helper.make_opsetid("", 17)],
    )
    checker.check_model(model)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, args.output)


if __name__ == "__main__":
    main()
