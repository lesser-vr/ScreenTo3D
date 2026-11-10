# Motion-aligned live depth history — 2026-11-06

## Result and scope

Implemented and enabled `motion` for the prepared-local DA2 Small/Base CUDA live
paths, including native/host delivery and the A/B/Small VFG comparison launchers.
It includes the preceding range/coverage behavior. Strength remains 0.5 and no
new GUI option is exposed. Existing running applications need a restart.

The public-video temporal proxy improves in all six model/clip combinations.
This establishes a bounded incremental correction, not Owl3D visual equivalence,
eye comfort, ground-truth depth accuracy, sustained 4K60 or game acceptance.
File/reference, RowFlow and VDA/oVDA paths are outside this change.

## Algorithm and ownership

- Two-direction NVIDIA hardware optical flow on RGB downsampled to maximum edge
  640, grid 2. The driver uses the engine's borrowed CUDA stream; temporal hints
  are disabled because forward/backward directions alternate.
- Warp the previous **pre-motion-correction** guided depth to the current frame.
  This does not recursively feed the new correction into history. Existing static
  pixel EMA and range state remain unchanged.
- Reject round-trip error >=0.75 flow-input pixels, 3x3 RGB mismatch >=0.06,
  normalized depth difference >=0.06, or current/warped/interpolation-corner depth
  span >=0.04. Very small motion remains with the existing static filter.
- Weight <=`0.45 * exp(-source_dt/0.1)` times three confidence factors, with a
  normalized depth step capped at 0.012. No future-frame buffering or inference
  skipping. A maximum 100ms source interval and explicit cut/resize resets bound
  history. Applied CPU flat-background refinement bypasses and invalidates it.
- Two float depth buffers plus one RGB history (~87MiB for 3840x2160) and bounded
  driver buffers are owned per renderer. Diagnostic masks/readback are explicit;
  normal rendering adds no host RGB/depth copy.
- Hash-pin both the module and accepted borrowed layouts. Load the NVIDIA driver
  from System32. Validate owner/device/dimensions/stream. Driver failures are
  terminal and visible; cleanup attempts all owned resources before destroying
  the borrowed renderer/stream. No DLL/model download or installation was added.

API conventions use the existing official API 2.0 headers and the
[NVIDIA NVOFA programming guide](https://docs.nvidia.com/video-technologies/optical-flow-sdk/nvofa-programming-guide/index.html).
This reuses the locally established NVIDIA dependency scope; it is not a public
redistribution/clean-machine qualification.

## Comparison contract and results

Control is the prior `range` depth. Each pair uses identical model inference,
RGB, range/static filtering and source time. Motion changes only projection
depth. Public clips are FloorballGame, OfficeWalk and ParkingGarage from the
existing attributed public-media fixtures. Each contributes 90 observations
(every second frame of the first 180, nominal 30Hz), with initial/midpoint/natural
cut resets excluded from temporal averages. Strength is 0.5, source 1920x1080.

Scoring uses independent OpenCV DIS MEDIUM flow at 480x270, interior/photometric
masking and source-width-scaled disparity residuals. Moving pixels have flow
magnitude >0.5 scoring pixels. Common baseline edges define the edge mask. This
is not a ground-truth or perceptual metric; it can reward temporal smoothing.
The analytic translation, depth-jump and newly-visible checks below constrain
incorrect smoothing separately.

| Model / clip | Mean residual px: range → motion | Moving-region reduction | Edge residual px: range → motion |
|---|---:|---:|---:|
| Base / Floorball | 0.04495 → 0.04372 | 2.76% | 0.28583 → 0.28121 |
| Base / Office | 0.22198 → 0.21431 | 3.44% | 0.39524 → 0.37918 |
| Base / Parking | 0.02631 → 0.02595 | 2.86% | 0.08107 → 0.07946 |
| Small / Floorball | 0.03756 → 0.03539 | 5.79% | 0.27766 → 0.27318 |
| Small / Office | 0.19958 → 0.18947 | 5.06% | 0.41995 → 0.40519 |
| Small / Parking | 0.02619 → 0.02579 | 3.76% | 0.10121 → 0.10005 |

Acceptance fractions are approximately 77.5%, 58.0% and 12.7% by clip. Mean
residual reductions are Base 1.37–3.45%, Small 1.53–5.76%. Accepted pixel count
does not mean every accepted pixel changes by a substantial amount.
Full-resolution synthetic 3px translation with interior depth noise reduces
normalized temporal MAE 0.03122→0.02256 (27.8%).

The 540 paired public observations were run on the initial algorithm DLL
`a727f194ac3b1a191d4ed3344de03c51fbce4174159772ca3c17b795e2e391c4`.
The final build changes only diagnostics/release validation, not flow, confidence
or blending. The valid public evidence is reused; final native/GUI/synthetic
checks below use the final pin.

## Cost and actual output

Isolated stream intervals include CPU enqueue gaps and driver work, not GPU
utilization or end-to-end display latency. Thirty warm samples of the correction
after postprocessing, using a translated public RGB frame:

| Source | Added median | P95 |
|---|---:|---:|
| 1920x1080 | 1.072ms | 1.855ms |
| 3840x2160 | 1.562ms | 2.573ms |

Actual Small VFG with 3840x2160 source and full 7680x2160 SBS texture, fitted into
a 1400x650 Qt output window, completed three 3-second measurement windows after
warmup. Native output was 77.51/77.92/78.03fps, with roughly 38.6–39.2 original
and 38.6–39.0 generated frames/s. Original source-age medians were 41.89/42.79/
41.95ms. This is a short functionality/throughput observation without a matched
range-only control in this run; it does not establish a speedup over previous
trials or physical 4K panel cadence. Prior Small VFG performance variability
remains relevant.

## Checks

- Final synthetic checks: exact fallback for newly visible RGB regions and large
  depth changes; cuts, backwards time, >100ms gaps and explicit invalidation;
  exact rejected pixels and stored pre-motion baseline; finite/capped correction.
- 16x16, 4096x16, 16x2160, 1080p and 4K motion sessions execute and release.
- 243 scoped CPU contracts pass, including checksum rejection before native load,
  failed-session rejection, foreign-thread protection and cleanup fault injection.
- 27 Small GPU resize fixtures plus 72 host/GPU/native cases over 1080p,
  ultrawide, portrait and 4K retain exact equality between delivery paths **with
  motion enabled on both sides**. This does not claim equality to range-only.
- Base and Small each pass six original/native VFG comparisons and generation at
  1080p and 4K.
- Actual Base A and Small VFG GUI checks pass start-button routing, strength 0.5,
  selected-model guard, capturable output/protected controls, cross-process
  recapture rejection, two-screen moves, fullscreen, hide/restore, stop/restart
  and zero native-pool/node cleanup.
- Small VFG 4K also passes resize, hide/restore, stop/clear, restart and preparation
  cancellation. No private source window was captured by these tests.
- Scoped Ruff and whitespace checks pass. Physical Owl3D comparison remains open.

## Reproduction and artifacts

Build: `scripts/build-live-motion.ps1`. The source/header/layout hashes are in
`out/live-motion/build-manifest.json`. Final module SHA256:
`4d84a0caec0b00ca8d3e3ff1974c0f52ea211028971e7bb3c19e64d58ce488b8`.
Existing range/Small/VFG borrowed-layout binaries are unchanged by this task.

Use the existing local Python environment and dependency paths with:

```text
v1/check_motion_history.py --model base --output <file.json>
v1/check_motion_history.py --model small --output <file.json>
v1/check_motion_history.py --synthetic-only --benchmark --output <file.json>
v1/test_small_gpu_input.py --quality motion --output <new-directory>
experiments/vfg/check_native_bridge.py --quality motion --model da2-base --output <new-directory>
experiments/vfg/check_native_bridge.py --quality motion --model da2-small --output <new-directory>
experiments/vfg/check_comparison.py --output <new-directory>
experiments/vfg/check_comparison.py --vfg --model da2-small --output <new-directory>
```

Raw results under `out/motion-history-20261106/`: `base-initial.json`,
`small-initial.json`, `contracts-final.json`, `benchmark.json`, `cpu-contracts.json`,
`small-parity/report.json`, `{base,small}-vfg-parity/result.json`,
`base-gui/smoke.json`, `small-vfg-gui/smoke.json`, `small-vfg-4k/report.json`.
`DEPTHSBS_STEREO_QUALITY=range` remains an explicit diagnostic control; normal
launchers use `motion`. This task did not commit or push changes.
