# Radius-4 guide lightweight accumulation — 2026-11-06

## Implementation and scope

The prepared-local radius-4 guided filter now accumulates each short box sum in
two FP32 components. Explicit round-to-nearest TwoSum additions retain the low
residual; the final component combination and mean scaling remain FP64, with
the original float products, coefficient calculation, epsilon and conversion.
There is no downsampling, smaller radius, extra frame buffer, guide bypass or
change to temporal policy. `LiveDepth` layout and ownership are unchanged.

This primarily affects Performance/DA2 Small and the explicit ZipDepth trial.
Balanced/Base radius 8 and other radii keep their existing calculations. TensorRT
model precision, source geometry, strength 0.25/detail and VFG default-off are
unchanged. Both host and native CUDA consumers use the same new guide result.

This is an intentional change of numerical representation, tested under the
declared error bounds below. Exact results in these fixtures are not a proof of
bit equality for arbitrary float inputs. The sum type is local to bounded,
normalized guide moments and regularized coefficients, not a generic FP64 substitute.

## Quality contract and candidate selection

`experiments/zipdepth/check_guide_precision.py` declares per-frame limits before
the candidate comparisons: guide **and post-motion** normalized-depth MAE <=1e-6,
max <=1e-4; SBS channel MAE <=0.05/255; in each eye, fraction of pixels with a
channel error >1 <=0.001; edge-band channel MAE <=0.20/255; temporal
difference-of-errors MAE <=0.10/255. All depth must be finite. Both sides receive
the same raw inference, RGB, clock, resets, range/history and projection settings.

- Plain FP32 sums passed the 180-frame synthetic probe but were not selected.
- A Kahan candidate returning only the rounded sum failed post-motion max error
  in 4/282 public frames, reaching 0.000834. Carrying its final correction into
  the mean reduced this to one failure but did not eliminate the gate crossing.
  Both candidates are rejected under this contract; the tolerance was not relaxed.
- The promoted two-component TwoSum candidate passes all comparisons below.
  Earlier failed candidates used the same depth limits; the final harness also
  resolves the actual Performance convergence 0.45/divergence 0.0045 and scene
  threshold 0.18 instead of the exploratory 0.5/0.0065/0.24 values.

| Matched comparison | Frames | Largest guide/post-motion depth error | Final SBS RGB difference |
|---|---:|---:|---:|
| Flat/dark/low-contrast/thin-line/step/random; five aspect/size cases through 4K, shifts/cuts | 180 | 0 | 0 |
| ZipDepth: three public 1080p clips and an upscaled OfficeWalk 4K segment | 282 | 0 | 0 |
| Small: same public corpus | 282 | 5.96e-8 | 0 |
| ZipDepth: genuine native-4K Jockey and Beauty | 24 | 0 | 0 |
| Small: same genuine native-4K clips | 24 | 0 | 0 |

All **792 compared frames have byte-identical SBS RGB**, including alpha=255
validation. The Small depth difference is one float32 ULP at that magnitude.
Each ordinary public clip supplies 90 consecutive observations at 60Hz; cuts
are forced at 45 plus shared scene detection. The upscaled segment has 12 frames
and a midpoint reset. Each native-4K clip supplies frames 120..131 at its original
120Hz clock, with a midpoint reset. Native clips are CPU-decoded for paired
quality inputs; the separate performance test uses actual WGC/mpv capture.
Those short native-4K segments check original texture detail, not sustained quality.

The existing public-media and HFR hashes/provenance are reused. No private input
was captured. A saved OfficeWalk original/candidate/16x-difference crop was also
inspected; it matches the zero-error result. No new physical Owl3D or binocular
comfort acceptance is claimed.

Quality records: `out/guide-compensated/quality-{synthetic,public}-final.json`,
`quality-public-final-small.json`, `quality-native4k-final{,-small}.json`.
Rejected candidate reports/manifests remain in that directory; `guide-fp32`
contains the plain-sum synthetic probe. A companion-build attempt initially
encountered a loaded DLL lock; it did not replace that DLL. The completed build
uses a separate companion-only scope and the validated depth binary.

## Real native 4K measurement

RTX 5090/driver 621.14, configured 480W limit unchanged. Pinned genuine UVG
Jockey 3840x2160/120fps through owned mpv/WGC, ZipDepth's unchanged 704x384 FP16
plan, native 7680x2160 window, strength 0.25/detail, VFG off. Baseline is the
previous **bitmap resolve plus early pacing** product, not the older slower
pre-bitmap path. `gpu_load_baseline.guide_worker` selects the prior fixed hashes
and keeps the current pacing. It is a benchmark-only comparison, not a fallback.

Five 10-second windows after a three-second warmup per session. FPS/age values
are medians across windows; whole-device GPU/power are means of 200ms samples
inside those windows. Clocks remain driver-controlled. Sessions run sequentially
with no concurrent GPU tests; the 60 cap is repeated in reversed candidate/control
order because its tail-latency behavior needed confirmation.

| First pair | Actual native FPS (range) | GPU activity | Power W | Callback age P50 / P95 ms |
|---|---|---:|---:|---:|
| Before, unlimited | 93.80 (93.68–94.50) | 79.62% | 299.02 | 17.63 / 22.24 |
| After, unlimited | 119.78 (119.69–119.80) | 66.45% | 290.69 | 11.75 / 13.71 |
| Before, 60 cap | 54.59 (54.20–55.00) | 40.06% | 187.19 | 16.29 / 19.25 |
| After, 60 cap | 53.20 (52.90–53.80) | 31.20% | 171.96 | 14.49 / 27.76 |

Unlimited improves 27.7% and is now limited by the roughly 119.8fps source;
this does not measure an unrestricted maximum. GPU activity falls by 13.17
percentage points while processing more frames. Whole-device memory is 6794MiB
in all four sessions; this is not application allocation or a leak measurement.

The reverse-order 60-cap pair reproduces the tradeoff: before/after output
54.50/53.50fps, GPU 39.95/31.10%, power 185.24/173.16W, P50 age 16.24/14.46ms,
and median window P95 age 19.23/31.65ms. Thus **do not claim improved capped
smoothness or all-percentile latency**: output is about 1–1.4fps lower and late
frames have greater age. The work/presentation scheduling interaction remains
unresolved; the guide's shorter kernel time alone cannot attribute its cause.
Keep this as an explicit output-timing follow-up rather than hiding it behind
the improved average cost or unlimited FPS.

All six sessions have 100% distinct-ID age sample coverage and zero live native
nodes/pools after stop. Counts are distinct Qt `afterFrameEnd`, not physical
scanout or panel latency; GPU metrics include player/compositor/desktop. This is
one public clip in bounded sessions, not long-session/game/hardware qualification.

Raw: `out/public-hfr/{Jockey-zipdepth-,}guide-{before,after}-{0,60}{,-repeat}.json`
(repeat only for 60). Aggregates: `out/guide-compensated/summary.json` and
`cap60-repeat-summary.json`. Reproduce with `gpu_telemetry.py --model zipdepth
--cap N --repeats 5 --tag NEW`, adding `--guide-baseline` for the prior product.

## GPU attribution and runtime regression

Separate eight-second Nsight captures isolate the four guide kernels. Their
average summed duration falls **3.6043→0.8549ms/frame (76.3%)**, and share of
summed CUDA kernel time falls 56.3→22.3%. The new trace has 957 calls of each
guide kernel; compare per-call durations, not aggregate totals from different
frame counts. `out/guide-compensated/profile.nsys-rep` and `stats_*.csv` are separate
from the uninstrumented performance table. The prior trace is in
`out/gpu-load-opt/`. This guide share is not whole-GPU utilization.

- Small actual GPU preprocessing: 27 cases; actual inference/postprocessing and
  host/native output: 72 cases across wide/portrait/4K, all differences zero in
  the established delivery comparison. This is additional to the before/after
  quality corpus above.
- Six host/native/VFG-original geometry cases retain exact output and eye order.
- ZipDepth's 36-frame exact-RGB reuse/stale-generation/closed-engine regression passes.
- Actual capturable ZipDepth static launcher at 30 cap passes three sizes, active
  square/landscape resize, hide/restore, stop/restart and zero-resource cleanup.
- Actual Base/Small VFG off/on option test passes five sessions, including Small
  4K resize, unsupported-path rejection, immutable running settings and cleanup.
  VFG bridge kernels themselves are unchanged; this is compatibility, not a new
  interpolation-quality/performance claim.
- 35 focused output/ownership/motion/RowFlow-trust/VFG contracts pass.

Runtime artifacts are under `out/guide-compensated/{geometry.json,small-validation/,
vfg-validation/,contracts.log,regression.log}`, plus
`out/zipdepth-reuse-guide.json` and `out/zipdepth-launch-static-smoke-cap30-guide.json`.
`scripts/check-guide-runtime.ps1` runs the scoped checks with fresh output folders.

## Prepared-local build

`scripts/build-gpu-load-opt.ps1` now defaults to `guide-compensated`. The old
`gpu-load-opt` baseline binaries remain intact; new builds still require explicit
validated pins. `-DepthOnly` and `-CompanionsOnly` support staged validation.
No portable bundle, commit or push was produced.

| DLL | SHA-256 |
|---|---|
| live_depth.dll | `cdb88564014c7253e37ca96e4475f45f132aa366c81411b60b0577f60e510998` |
| live_texture_runtime.dll | `75cf040ea9ab2c2f226818faf07a6746e146676d69f78242b70cf93ba25232cd` |
| small_input.dll | `ca84bb54ce84d426d2af383d0b8971966b10e12bae8dc851c892f3474b43c408` |

Compiler flags, all included source hashes and the OpenCV notice accompany the
build. Allocator/borrowed-layout pins for motion/native/VFG/RowFlow are updated
together. No generic loader bypass or automatic precision fallback is introduced.
