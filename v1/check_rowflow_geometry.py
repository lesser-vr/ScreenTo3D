"""Physical eye-order check using the pinned optional RowFlow model (eager only)."""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch

from screento3d_app import rowflow
from screento3d_app.live_policy import resolve_live
from tests.test_stereo_geometry import geometry_fixture


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cls, warp = rowflow.implementation()
    assert hashlib.sha256(rowflow.WEIGHT.read_bytes()).hexdigest() == rowflow.WEIGHT_HASH
    checkpoint = torch.load(rowflow.WEIGHT, map_location="cpu", weights_only=True)
    assert checkpoint["name"] == "sbs.row_flow_v3" and checkpoint["kwargs"] == {}
    renderer = rowflow.RowFlowRenderer.__new__(rowflow.RowFlowRenderer)
    renderer.engine = SimpleNamespace(torch=torch)
    renderer.policy = replace(resolve_live("balanced"), convergence=.5)
    renderer.model = cls().eval().cuda()
    renderer.model.load_state_dict(checkpoint["state_dict"], strict=True)
    renderer.model.delta_output = renderer.model.symmetric = True
    renderer.warp = warp
    frame, depth = geometry_fixture(640, 360)
    frame[:, 312:328] = (255, 80, 40)
    renderer.rgb = torch.from_numpy(frame).cuda()
    renderer.aligned = torch.from_numpy(depth[0]).cuda()
    with torch.inference_mode():
        result = renderer._render_pixels(compiled=False).cpu().numpy()
    measured = {}
    for name, row in zip(("far", "screen", "near"), (60, 180, 300)):
        positions = []
        for eye in (result[row, :640], result[row, 640:]):
            profile = eye[:, 0].astype(float)
            assert profile.sum() > 0
            positions.append(float(profile @ np.arange(640) / profile.sum()))
        measured[name] = positions[0] - positions[1]
    assert measured["far"] < -4 and measured["near"] > 4 and abs(measured["screen"]) < 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dict(passed=True, left_minus_right=measured,
        scope="Pinned model and product pixel packing; eager geometry only, not compiled/perceptual acceptance"), indent=2))
    print(json.dumps(measured))


if __name__ == "__main__":
    main()
