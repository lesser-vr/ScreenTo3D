# oVDA mixed FP16 and aspect-fit, 2026-11-09

The source application's c16 FP32 path now accepts arbitrary aspect ratios
within the existing 16..4096 by 16..2160 input bounds. FP16 candidates remain
isolated experiments; neither changes the normal loader allowlist or default.
No portable oVDA runtime or weights were added. The existing source-only,
non-commercial license scope remains applicable.

## Geometry

`ovda_geometry.py` selects a matching installed native canvas when available.
Other sizes use the installed canvas with the largest content fraction. Model
input receives replicated-edge padding; model depth is cropped to that rectangle
before interpolation to the original source. RGB and SBS eyes keep their source
geometry. Source-size changes continue to reset/recreate the temporal binding.
Host, device and buffered-device output share the same transform and restoration.

`experiments/ovda/check_aspect_fit.py` passed 15 byte-exact native preprocessing
comparisons across five sizes and zero/one/random RGB patterns. Six additional
geometries included ultrawide, portrait, square, extremely wide and narrow inputs;
synthetic sentinel padding never entered restored depth. Four binding and two
installation contracts pass, including fitting a missing native profile into
another installed canvas and invalidating selection after bad preflight.

Actual FP32 host/device depth matched exactly on three public frames each at
3440x1440, 1080x1920, 1024x1024, 1056x608 and 1280x720, exercising all three
installed canvases. Artifacts: `out/ovda-aspect-fit-20261109/cpu.json` and
`runtime.json`.

Actual Qt/WGC/native Half Top-and-Bottom checks passed at ultrawide, portrait and
square sizes, including fullscreen/Escape, minimize, output close, restart
placement, both displays and preparation cancellation. The fractional-DPI square
fixture required Win32 client-pixel metadata rather than rounding Qt logical
pixels; the test now verifies the actual captured geometry and odd-axis packing.
Artifacts: `out/ovda-aspect-ultrawide-20261109/`,
`out/ovda-aspect-portrait-20261109/` and `out/ovda-aspect-square-20261109-r2/`.
These do not establish physical stereo comfort or quality at extreme ratios.

## Precision candidates

All new plans were built on the local RTX 5090, driver 621.14, TensorRT
11.2.1.2, with TF32 disabled. The fixed 518x924 c16 ONNX source is the previously
validated export with SHA256
`586a7ca21a7d91360e4e2b52912685875e50f07cd18a42ed34a13e529f4ba545`.

| Variant | Change | Plan SHA256 |
|---|---|---|
| Fresh FP32 control | Original graph, same current device/build procedure | `7bd4916e0104a1306c99dd0bb5a37e8bf27aed0f8ac698b5f35f1076147b0e75` |
| Encoder FP16 | Patch embedding and encoder linear projections | `d4b242984e6e1dc63a6857462954bb71e699a482d6af3dbd79531279762b41b3` |
| Encoder + spatial FP16 | Above plus rounded spatial QK/AV operations, fused by TensorRT | `394894301beee2302decaf43e7dd4912c043cae469a07f19f4848774a5eb0ec1` |

Temporal processing, cache tensors, depth head and floating I/O retain FP32.
Mask/position inputs remain INT64. Engine inspection records Half bindings and
fused spatial attention; internal fused-kernel accumulation/Softmax precision is
not independently established. Plans/graphs/inspection are under
`out/ovda-precision-20261109/` and `out/ovda-precision-control-20261109/`.
The experimental runtime loads only these explicitly pinned local plans.

The old deployed FP32 plan prints a TensorRT device-model compatibility warning.
To separate that from performance comparisons, all three measured variants were
built on the current device. The fresh FP32 control matched the old FP32 depth
at atol=rtol=.001 on 144 public frames with independent histories.

## Matched depth and native SBS

FloorballGame, OfficeWalk and ParkingGarage use the pinned public UVG-VCM
previews, with source hashes retained in the report. Independent model/cache and
renderer histories processed 360 matched frames across 1280x720, 3440x1440,
1080x1920, 1024x1024 and scaled 3840x2160. Each run uses the same 518x924 canvas
for all variants, isolating precision from production best-canvas selection.
Sequences extend beyond the 16-slot cache capacity; histories reset between clips.
Strength is 0.5, VFG off and Full SBS. Native texture readback is diagnostic only.

| Size | Encoder + spatial mean raw depth error (% of reference P2-P98) | Mean SBS RGB error (0-255) |
|---|---:|---:|
| 1280x720 | 0.01750% | 0.02287 |
| 3440x1440 | 0.01668% | 0.02542 |
| 1080x1920 | 0.04148% | 0.03755 |
| 1024x1024 | 0.02307% | 0.02597 |
| 3840x2160 | 0.01492% | 0.02637 |

The worst frame-mean raw depth error was 0.11594% of reference range; worst
frame-mean SBS error was 0.07888/255. At most 0.2846% of pixels in one frame had
any channel difference above 8. These are numerical differences, not depth
accuracy against ground truth or perceptual flicker/comfort measurements.
All output tensors were finite. Both FP16 recipes exceeded strict per-pixel
depth/cache atol/rtol .001 checks, so this is a precision tradeoff rather than
behavior-preserving parity. No production FP16 promotion was made.

At scaled 4K, the matched replay's median TensorRT-only stream interval was
16.28 ms for FP32, 14.78 ms for encoder FP16 and 6.18 ms for encoder + spatial
FP16. These intervals exclude capture, preprocessing, rendering, readback and
display, and are not end-to-end FPS. Artifacts:
`out/ovda-precision-evaluation-synchronized-20261109/report.json` and
`out/ovda-precision-control-20261109/comparison-synchronized.json`.

The first diagnostic pass lacked an owner-stream fence before CPU depth readback
after asynchronous depth restoration. Its depth metrics are invalidated in
`out/ovda-precision-evaluation-20261109/readback-audit.json` and are not used here.
The synchronized rerun and fresh FP32 control above supersede those measurements.

## Actual native throughput and GPU use

An owned window played the pinned FloorballGame preview with a 16 ms source timer
(approximately 62.5 source advances/s). The ordinary mapped WGC/oVDA CPU
preprocessing path generated actual native Full SBS with strength 0.5, VFG off
and no app FPS cap. 4K is a scaled public source, not native game rendering or
4K hardware decoding. Variant order was FP32/encoder/spatial followed by the
reverse, at each resolution. Every session warmed for three seconds then measured
two adjacent three-second windows: four windows per variant and size.

| Per-eye size | Variant | Mean native FPS | Mean device GPU |
|---|---|---:|---:|
| 1920x1080 | FP32 | 25.08 | 45.75% |
| 1920x1080 | Encoder FP16 | 26.04 | 42.50% |
| 1920x1080 | Encoder + spatial FP16 | 29.97 | 31.96% |
| 3840x2160 | FP32 | 9.20 | 50.57% |
| 3840x2160 | Encoder FP16 | 9.55 | 49.64% |
| 3840x2160 | Encoder + spatial FP16 | 10.62 | 45.79% |

FPS counts distinct native submissions, not physical presentation. GPU readings
are device-wide NVML samples every 0.5 s, including public playback, desktop and
other clients; they are not process-exclusive. Source capture outpaces inference,
so the current oVDA skip/reset policy still applies. Model speedup therefore does
not establish steady full-history depth quality at that input rate. All twelve
sessions stopped with zero native pools/nodes. The spatial recipe improved actual
output about 19.5% at 1080p and 15.5% at 4K; inference alone is not the remaining
end-to-end bottleneck. Artifacts: `out/ovda-precision-native-20261109/report.json`.

Reproduction tools are `precision_trial.py`, `check_precision_control.py`,
`evaluate_precision.py --reference fp32-current`, `benchmark_precision_live.py`,
`check_aspect_fit.py` and `check_aspect_runtime.py` in `experiments/ovda/`.
Their fixed pins refer to these locally built trial plans. The initial FP16
graph candidate rejected in September remains separate historical evidence.
