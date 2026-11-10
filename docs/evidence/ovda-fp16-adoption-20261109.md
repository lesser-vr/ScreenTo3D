# oVDA 518x924 mixed FP16 adoption — 2026-11-09

Ordinary source live and file oVDA now select the previously validated
encoder+spatial mixed-FP16 engine at 518x924. Temporal blocks, cache, depth head
and floating I/O retain FP32. c16 capacity, depth-range stabilization, live pixel
EMA, source geometry and output format choices are unchanged. This does not
change the application's DA2 Small default or add a precision/resolution option.

The normal allowlist contains the adopted 518x924 artifact only. Other source
ratios aspect-fit into that canvas; the source/eye dimensions are preserved.
UI help, CLI/backend diagnostics, engine telemetry and read-only setup inventory
identify mixed FP16. Archived FP32 plans remain on disk for explicit diagnostic
comparisons but are not automatic loading alternatives.

## Installed artifact and existing evidence

- Canonical path: `out/ovda-local/518x924-fp16/model.plan`.
- Bytes: 91370692.
- SHA256: `394894301beee2302decaf43e7dd4912c043cae469a07f19f4848774a5eb0ec1`.
- Source: the exact validated bytes under
  `out/ovda-precision-20261109/encoder-spatial/model.plan`.
- Installation verified source bytes through the new allowlist, wrote a sibling
  temporary file, replaced the destination atomically and checked the installed
  bytes again. No old FP32 artifact was overwritten.

The [resolution/precision comparison](ovda-resolution-fp16-20261109.md) remains
applicable: the adopted plan bytes and live filters are identical to its passing
518x924 candidate. That comparison measured nine public cases/1002 frames and
short actual native Half TB 4K output 46.16->62.42 FPS, device-wide GPU
86.95->64.55%. The optimized rate reaches the ~62.5 Hz test-source ceiling;
it is not measured maximum model throughput or physical display scans.
Those are reused measurements, not a new benchmark after copying the artifact.

## Adoption checks without trial routing

All following runtime tests use the normal registry and canonical installation,
without process-local trial allowlist/worker substitutions:

- Fifteen affected unit checks pass: profile selection, missing/corrupt artifact
  rejection, no old-FP32 fallback, precision help, installation inventory and
  unchanged live model policy.
- `check_aspect_runtime.py`: 24 actual frames across ultrawide 3440x1440,
  portrait 1080x1920, square 1024x1024, original 1056x608, 1280x720, 4:3 960x720,
  1920x1080 and 3840x2160. Host/device restored depth is exact in every comparison;
  all select the adopted 518x924 canvas.
- Normal QML/WGC/native Half TB start, live input resizing, both-monitor output
  movement, F11/Esc, minimize/continue, X/button stop, restart placement and
  preparation cancellation pass. Stop releases native pools/nodes. This GUI
  fixture uses isolated preferences, preserving normal user selections.
- The normal file CLI converts all 360 frames of the pinned public FloorballGame
  six-second preview to H.264 Half TB, with the adopted plan hash and mixed-FP16
  backend/resource telemetry. FFprobe confirms 1920x1080, 60/1, 360 decoded frames,
  duration 6.000 seconds. Full FFmpeg decode completes without errors. The source
  has no audio, so this does not extend audio acceptance.

Artifacts under `out/ovda-fp16-adoption-20261109/`:
`aspect-runtime.json`, `gui/report.json`, `file-run.jsonl`, `file-probe.json` and
`file-half-tb.mp4`. The file job took 34.4 seconds in its existing CPU-preprocessed,
host-output/CUDA-projection pipeline; it is a correctness check, not the native
live GPU path's throughput. It retains every decoded frame.

The runtime remains source-only and under the existing non-commercial/license
scope. No portable package, other-GPU support, normal-speed binocular review or
physical Owl3D comfort acceptance is added by this adoption.
