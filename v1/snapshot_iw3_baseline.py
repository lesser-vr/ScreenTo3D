"""Read-only, allowlisted iw3 desktop settings/artifacts; no imports or capture."""

import argparse
import ast
import configparser
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

FIELDS = {
    "ComboBox": ["cbo_synthetic_view", "cbo_method", "cbo_depth_model",
                 "cbo_stereo_format", "cbo_view_mode", "cbo_screenshot"],
    "CheckBox": ["chk_ema_normalize", "chk_preserve_screen_border", "chk_cross_eyed",
                 "chk_pad_16_9", "chk_compile"],
    "nunif.EditableComboBox": ["cbo_divergence", "cbo_convergence", "cbo_zoed_resolution",
                              "cbo_edge_dilation", "cbo_edge_dilation_y", "cbo_ema_decay",
                              "cbo_foreground_scale", "cbo_stream_fps", "cbo_stream_height"],
}
FILES = ["iw3/desktop/gui.py", "iw3/desktop/utils.py", "iw3/depth_anything_model.py",
         "iw3/stereo_model_factory.py", "iw3/utils.py",
         "iw3/pretrained_models/hub/checkpoints/depth_anything_v2_vits.pth",
         "iw3/pretrained_models/hub/checkpoints/iw3_row_flow_v3_sym_20250628.pth"]


def file_record(path):
    if not path.is_file():
        return {"status": "missing"}
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"status": "present", "bytes": path.stat().st_size, "sha256": digest}


def read_settings(path):
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("Settings file exceeds diagnostic size limit")
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(path, encoding="utf-8-sig")
    settings = {}
    for group, fields in FIELDS.items():
        for name in fields:
            section = f"Persistence_Options/{group}/{name}"
            option = "Selection" if group == "ComboBox" else "Value"
            if not parser.has_option(section, option):
                settings[name] = None
                continue
            value = ast.literal_eval(parser.get(section, option))
            if (not isinstance(value, tuple) or len(value) != 2
                    or value[0] not in ("str", "bool", "int")
                    or not isinstance(value[1], str)):
                raise ValueError("Unexpected persisted settings type")
            settings[name] = value[1]
    return settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.repository.resolve(strict=True)
    if args.output.exists():
        raise ValueError("Fresh output directory required")
    config = root / "tmp/iw3-desktop.cfg"
    report = {"schema": "depthsbs.iw3-baseline-snapshot.v1",
              "captured_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Saved settings and installed artifact inventory only. No active profile, "
                       "runtime rates, output geometry, FG or HMD verification. Network, auth, "
                       "window and monitor identity fields deliberately omitted.",
              "commit": subprocess.check_output(
                  ["git", "-c", f"safe.directory={root.as_posix()}", "-C", str(root),
                   "rev-parse", "HEAD"], text=True).strip(),
              "settings_file": file_record(config), "settings": read_settings(config),
              "files": {name: file_record(root / name) for name in FILES}}
    args.output.mkdir(parents=True)
    destination = args.output / "report.json"
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(destination)


if __name__ == "__main__":
    main()
