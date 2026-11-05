# Base GPU capture and preprocessing — 2026-11-05

Historical local implementation/test record. Current behavior is owned by
PRODUCT.md and current support/measurement summaries by implementation-status.md.
No model weights, precision, source/per-eye geometry, stereo strength or output
transport default changed. This implements the first item of the Veyra/iw3 review.

## Implementation and comparison contract

- Base window GPU sessions select owned WGC → D3D11 → CUDA capture. Monitor and
  other model paths retain mapped capture. Explicit diagnostic selection is
  documented in `docs/models/da2-base.md`; no new GUI control is introduced.
- Two WGC buffers have fixed 4096x2160 capacity, 67.5 MiB of BGRA storage excluding
  driver overhead. A replaceable latest frame and one acquired frame bound
  ownership. Only actual ContentSize is copied into the registered bridge/CUDA
  tensor. CUDA completion precedes release; this performs device copies and a
  synchronization, not zero-copy. The CUDA adapter is matched to D3D11.
- `base_input.cu` preserves OpenCV's half-pixel/A=-0.75 float32 coefficients,
  float64 separable cubic accumulation, division and normalization, final FP32,
  model-only replicated padding and original depth unpadding/upscaling. Compilation
  disables FMA. RGB and pitched BGRA inputs are supported.
- Same-stream GPU RGB feeds both inference and the existing source-depth stereo
  consumer. Exact 32x32 scene pixels and border samples cross to CPU. Existing
  conditional flat-background refinement explicitly reads full RGB/depth back
  and uploads refined depth. It is not removed to obtain a speed improvement.
- Source HWND/PID, desktop, visibility, SDR and bounds validation remain. Capture
  exclusion/OS border are preserved. Resize retires output consumers before
  replacing their engine stream. No captured private pixels were recorded by
  these tests; GUI/capture fixtures are generated or the public test corpus.
- OpenCV-derived resize arithmetic retains its copyright/license in the source,
  generated `out/base-input/OPENCV-NOTICE.txt`, and distribution notices. No Veyra
  GPL code or iw3 runtime was copied into the app.

Final local DLL SHA-256:

| Artifact | SHA-256 |
|---|---|
| base_input.dll | `0af243632a9bd59e71cdca6abf0c61a44b4b73f161f86dc1d4df24897f8843cb` |
| gpu_capture.dll | `adebe984ad7b66a35e007a99921e810694b1aa822f08ca0dea17b7afc6326a68` |
| live_depth.dll | `e88697254fa9d81ade5d19b84b2f9107d5d1211fbeb9243cb4ec0af77b7ae6df` |

The LiveDepth struct layout is unchanged; the source-depth entry point additionally
accepts device RGB. The native borrowed-layout pin was updated and native output
pixel/lifecycle checks passed. Builds use CUDA 13.1/MSVC and the existing SM120
scope. Runtime is RTX 5090, driver 621.14, TensorRT 11.2.1.2, PyTorch 2.7.1+cu128,
OpenCV 4.13.0 and Qt 6.10.2. Model plan hashes/licenses are unchanged.

## Correctness and lifecycle evidence

- `out/base-input-validation-20261105/report.json`: 66 combinations of eleven
  source sizes, three patterns and two model profiles. Both RGB and pitched BGRA
  preprocessing are bit-exact; all 32x32 scene thumbnails match OpenCV exactly.
  Five wrong-stream/device/dtype/layout checks reject before useful submission.
- `out/base-device-input-final-parity-20261105/report.json`: 24 real Base cases
  across 1080p, ultrawide, portrait and 4K, including cuts and flat background.
  Raw depth is exact against the original host engine; GPU-input versus
  CPU-input SBS is exact; host-output versus native SBS is exact. Legacy CPU
  stereo comparisons pass the existing numerical tolerances. Pending/released
  token validation is exercised.
- `out/base-gpu-capture-fixed-validation2-20261105.log`: 30 settled static-window
  captures over ten starts and repeated size changes; color, timestamp bounds,
  owner-thread rejection, initial/active hidden-source rejection passed.
- `out/base-gpu-input-gui-20261105/report.json`: actual QML button start/stop,
  sole output, F11/Escape, minimize, X-to-stop, restart placement and preparation
  cancellation passed with the new input path.
- `out/base-gpu-input-final-lifecycle-20261105/report.json`: final native GUI
  input resize/lease retirement, hidden/restored output, fullscreen/Escape,
  stop/clear, restart/source loss and owned-worker crash cleanup passed. Assertions
  verify zero remaining output pools/nodes after shutdown.
- `out/base-gpu-input-final-unit-20261105.log`: 39 selected input, mode, capture,
  scene-history and transport protocol tests passed.
- `out/base-input-small-regression-20261105.json`: five actual DA2 Small/native
  cycles passed nonfinite rejection, poisoned-session checks, repeated close,
  wrong-thread close and closed-token rejection with the rebuilt shared DLL.

These are technical and bounded GUI checks, not continuous binocular/HMD review,
physical device-loss recovery, long-soak, monitor GPU capture or general support.

## Matched pipeline measurements

Public FloorballGame source in a separate process, Balanced/Base, target 60Hz,
6s discarded warmup followed by five 6s windows. Original source pixels are a
1080p excerpt scaled to each test size; 4K processing produces 7680x2160 Full SBS
in a fitted output window, not 1:1 physical scanout. No frame generation.

| Per eye | Original input, host output | GPU input, host output | Original input, native output | GPU input, native output |
|---|---:|---:|---:|---:|
| 1920x1080 | 18.21 fps | 26.69 fps | 21.20 fps | 32.33 fps |
| 3840x2160 | 6.78 fps | 12.56 fps | 9.27 fps | 23.87 fps |

Host output counts callback submission proxies; native counts distinct Qt
afterFrameEnd IDs. Each table value is the median of five windows. 4K ranges:
original host 6.62–6.96, GPU host 12.39–12.59, original native 9.11–9.28,
GPU native 23.69–24.03 fps. These do not establish sustained 30/60Hz support.

At 4K, sampled aggregate depth-stage median fell from 95.52 to 39.89ms with host
output and from 90.80 to 31.97ms with native output. It includes preprocessing,
model execution, interpolation and validation, not pure-model time. Native SBS
median was 9.87ms and worker total 42.87ms after the change. Host output still
incurs full SBS readback/CPU delivery; its SBS median was 35.60ms.

For the normal-background native fixture, explicit H2D counters fell from
30,626,784 bytes per 4K frame to zero. Explicit D2H is now 39,076 bytes per frame
(thumbnail + border + validity), rather than a full captured RGB readback.
This excludes driver/internal traffic and the model's scalar finite check;
conditional background cases can transfer full RGB/depth. Device copies remain.

Raw measurement records and aggregation:

- `out/base-input-cpu-bench-20261105/`
- `out/base-input-final-host-20261105/`
- `out/base-input-cpu-native-bench-20261105/` (five valid 1080p windows only)
- `out/base-input-cpu-native-4k-20261105/`
- `out/base-input-final-native-1920x1080-20261105/`
- `out/base-input-final-native-3840x2160-20261105/`
- `out/base-input-summary-20261105.{py,json}`

The final host benchmark used the same fixed-capacity capture implementation
before an adapter-enumeration HRESULT check was added; that check changes failed
startup only. Its report predates the corrected copy-description text/snapshot;
transfer counters and explicit input environment remain the measurement basis.
Final native runs record the final capture hash and corrected copy description.

Reproduce with `v1/benchmark_live_modes.py --sizes <size> --modes balanced --hz 60
--source FloorballGame --source-process --seconds 6 --repeats 5 --path <gpu|gpu-texture>
--output <fresh-directory>`. Original input explicitly sets
`DEPTHSBS_GPU_CAPTURE=0` and `DEPTHSBS_BASE_INPUT=cpu`; the updated path uses
default settings. Native measurements use a fresh process for each size.

## Failures and remaining limits

The first adaptive-pool capture prototype sometimes stalled or encountered a
short old-size surface during rapid static-window resize/restart. Fixed bounded
WGC capacity removes pool recreation; the 30-case repeated test and final GUI
lifecycle pass. The fixture now waits for its actual repaint to settle rather
than assuming ContentSize means its first resized frame is already painted.

The native output benchmark's 1080p → stop → 4K session sequence twice failed
with `Native texture wrapping failed`: once with original CPU input, once with
GPU input. Each first-size measurement completed; failed sequences are retained.
Independent fresh 4K sessions and the bounded resize/restart lifecycle passed.
This pre-existing output-boundary issue is not fixed here and native output
remains experimental. The TensorRT device-plan compatibility warning also remains.
No claim is made about Owl3D/headset acceptance or a portable package rebuild.
