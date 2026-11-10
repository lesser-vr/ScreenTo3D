# 4K GPU load and fresh-input pacing — 2026-11-06

## Delivered change

- Shared CUDA stereo resolve now uses 32-pixel occupancy words, coalesced owner
  reads and nearest occupied-word lookup. Source selection, quantized depth
  comparison, left-side ties and empty-row fallback retain the reference behavior.
- Radius-4 guidance has a fixed-radius 2-D launch with the original double
  addition order and float products/conversions. Other radii are unchanged.
  The live profile does **not** establish a guide-stage speedup; this remains
  the largest optimization opportunity.
- Capped non-VFG native workers wait for their deadline and a writable texture
  BEFORE acquiring the latest source/inferencing. They do not precompute a stale
  result while both slots are occupied. One slot may remain displayed; requiring
  both free would deadlock the retained display lease. Existing stop/parent checks,
  timeout, consumer pacing and GPU-lease retirement remain active.
- Unlimited stays the default. Strength 0.25, `detail`, resolution, model plans,
  VFG default-off and capture exclusion are unchanged. VFG keeps its existing
  producer/timeline and bridge projection kernels. Host producer pacing is unchanged.
- Source-depth diagnostic `gpu_stage_ms` is now `null`, with explicit availability
  and scope fields, instead of misleading uninstrumented zeroes. Measured CPU
  background time is reported separately. This does not add CUDA stage events.

## Paired native measurement

RTX 5090, driver 621.14, configured 480 W limit unchanged. Owned mpv plays the
previously pinned public UVG Jockey at native 3840x2160/120 FPS; WGC arrival stays
about 119.7–119.9 FPS. ZipDepth uses the same pinned 704x384 mixed-FP16 exact-forward
plan, strength 0.25/detail, VFG off and windowed native 7680x2160 output.

Each cell is from five 10-second windows after a 3-second warmup in one session.
Before/after runs are sequential, not randomized. `gpu_load_baseline.py` selects
the exact old DLL pins and consumer-only pacing; it is a measurement-only path,
not an application fallback. FPS and age are medians across windows; GPU activity
and power are means from 200ms `nvidia-smi` samples within those windows.

| Revision | Output limit | Actual FPS | Whole-GPU activity | Power W | Callback-to-Qt age P50 ms |
|---|---|---:|---:|---:|---:|
| Before | Unlimited | 83.60 | 82.04% | 298.88 | 19.00 |
| After | Unlimited | 94.59 | 80.15% | 287.89 | 17.52 |
| Before | 60 | 55.80 | 48.75% | 221.21 | 43.11 |
| After | 60 | 54.49 | 40.06% | 184.16 | 16.31 |
| Before | 30 | 29.10 | 31.88% | 142.58 | 77.16 |
| After | 30 | 28.60 | 28.26% | 128.66 | 17.58 |

Unlimited throughput improves 13.1%. The 60 cap lowers activity by 8.69 percentage
points and power by 16.7%, with a 2.3% lower achieved FPS. The 30 cap lowers power
by 9.8%, with a 1.7% lower achieved FPS. These are caps, not a promise of exact
30/60 output. Software age falls by 62.2%/77.2% at 60/30 respectively.
Unlimited still uses substantial GPU activity because it processes more frames.

Age uses each distinct Qt `afterFrameEnd` ID minus its WGC callback timestamp;
all six runs have 100% ID sample coverage and zero live nodes/pools after stop.
This is not physical monitor latency or scanout FPS. Activity/power includes the
player, compositor and desktop; clocks follow the driver's normal response to
load. The result is not long-session, other-content or other-hardware qualification.

Raw: `out/public-hfr/opt-{before,after}-{0,30,60}.json`, corresponding
`Jockey-zipdepth-opt-*.json` and `.run.log`; aggregate
`out/gpu-load-opt/summary.json`. Reproduce with `gpu_telemetry.py --model zipdepth
--cap N --repeats 5 --tag NEW` (add `--baseline` for old behavior), then the
`summarize_gpu_opt.py` aggregator for the recorded tags.

## CUDA trace and rejected candidate

An 8-second Nsight trace (`out/gpu-load-opt/profile.nsys-rep`, `stats_*.csv`)
contains 1,528 eye-resolve calls. Average resolve time is 0.08377ms/eye,
0.16753ms per stereo frame, versus 0.63006ms/eye and 1.26011ms/frame in the
[prior trace](gpu-load-audit-20261106.md): about 86.7% less resolve kernel time.
Its share of summed CUDA kernel time falls from 17.1% to 2.6%.
The four guide kernels average about 3.60ms/frame versus 3.51ms previously;
they now account for 56.3% of summed kernel time. Do not infer a guide speedup
from the overall FPS gain or from its smaller diagnostic-copy timing.
Profiler runs are separate from the uninstrumented performance table.

A compensated float expansion with exact double fallback passed 12.6 million
adversarial partial-sum comparisons and exact image parity, but increased 4K
diagnostic postprocessing from roughly 7.4 to 11.8ms. It was rejected. Only the
original double arithmetic is in the promoted path. The isolated experiment is
`guide_sum_candidate.cuh`/`check_guide_sum.py`; rejected manifest/parity files
remain in `out/gpu-load-opt/*rejected-expansion.json`.

## Compatibility and correctness

- 132 serial-oracle resolve cases cover width 1..4096, odd/partial words, empty
  rows, holes, boundaries, depth ties and random owners. Eight larger performance
  fixtures also match (140 total). That microbenchmark's reference is serial; use the Nsight
  figures above when comparing to the previous product's parallel resolve.
- 48 matched-depth cases at six sizes, including portrait, square and 4K:
  aligned float32 depth is exact and native RGBA is byte-identical to the old
  pinned runtime. Old RowFlow bridge reads the new allocator's RGB/depth exactly
  at all six sizes. No `LiveDepth` layout fields changed.
- Small: 27 preprocessing cases and 72 actual inference/postprocessing/native
  cases pass at wide, portrait and 4K sizes; all recorded input, depth and SBS
  differences are zero in this fixture set.
- Six host/native/VFG bridge geometry cases retain identical pixels and eye order.
- ZipDepth: 36 native frames, including 18 exact-RGB depth reuses, pass across
  960x540, square and 4K, retaining stale-generation/close rejection.
- Actual capturable ZipDepth launcher: 30-cap static and 60-cap moving sources
  pass three sizes, active square/landscape resize, output hide/restore,
  stop/restart and zero-pool/node cleanup.
- Actual Base/Small desktop VFG off/on transitions, opt-in UI, unsupported-path
  rejection, hide/restore, Small 4K resize and cleanup pass across five sessions.
  VFG interpolation quality/performance is not newly qualified by this check.
- 35 focused unit/protocol tests pass. The final live profiler run also verifies
  that the source-depth stage timing report is explicitly unavailable.
- After all owned test processes exit, GPU activity returns to 0%, 25.26W,
  3936 MiB whole-device memory. This is an idle sample, not a process-memory metric.

Commands: `scripts/check-gpu-load-opt.ps1` (fresh output directories),
`v1/test_parallel_resolve.py --dll out/gpu-load-opt/resolve_probe.dll`, and
the presentation/native-delivery/live-boundary/motion/RowFlow-trust/VFG unit tests.
Artifacts: `out/gpu-load-opt/{parity.json,report.json,geometry.json,contracts.log,
small-validation/report.json,vfg-validation/result.json,regression.log}` and
`out/zipdepth-{reuse-gpu-opt,launch-static-smoke-cap30,launch-smoke-cap60}.json`.
These tests do not replace physical Owl3D binocular review.

## Prepared-local artifacts

`scripts/build-gpu-load-opt.ps1` builds the shared prepared-local runtime in
`out/gpu-load-opt`; `-Diagnostics` also builds the resolve and sum probes.
The OpenCV notice remains beside the binaries. Existing reference binaries are
preserved. New builds still require validation and explicit code-pin updates.

| DLL | SHA-256 |
|---|---|
| live_depth.dll | `a1abad814853a74890214f8cc95e9be853f107a7479ab3aad1afb0fda441afee` |
| live_texture_runtime.dll | `f6e71f9b19f496dd972a3c2b88943d4539924e63c374cbf149a5877a74d1715d` |
| small_input.dll | `a641facccfb24e60fc86debfdce4db795926e7a1c81b9a5ac545f4f3df20b857` |

Loader pins and validated borrowed-layout pins are updated together, including
motion history, native texture, VFG and optional RowFlow. No trust guard is
removed. The portable bundle is not rebuilt; this is the prepared local source app.
